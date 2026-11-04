import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react"
import { api } from "../../lib/api"
import type { AvatarStatus } from "../../lib/types"
import type { Page } from "../shell/navigation"

// three.js is only loaded when this page is opened.
const AvatarViewer = lazy(() => import("./AvatarViewer"))

type ActiveJob = { id: string; kind: "avatar" | "tryon" }

// Files fetched with the user's session become blob URLs; the previous one is released.
function useBlobUrl() {
  const [url, setUrl] = useState<string | null>(null)
  const current = useRef<string | null>(null)
  const set = useCallback((blob: Blob | null) => {
    if (current.current) URL.revokeObjectURL(current.current)
    current.current = blob ? URL.createObjectURL(blob) : null
    setUrl(current.current)
  }, [])
  useEffect(() => () => { if (current.current) URL.revokeObjectURL(current.current) }, [])
  return [url, set] as const
}

const message = (error: unknown, fallback: string) => (error instanceof Error ? error.message : fallback)

const PHOTO_TIPS = [
  "Full body, head to feet",
  "Standing straight, facing the camera",
  "Fitted clothes, good light",
  "Plain background, nobody else",
]

function Viewer({ url, label }: { url: string; label: string }) {
  return (
    <Suspense fallback={<div className="grid h-full place-items-center text-sm text-white/50">Loading viewer…</div>}>
      <AvatarViewer url={url} label={label} />
    </Suspense>
  )
}

// The user's 3D avatar: made once from a photo, then used by every virtual try-on in the app
// (Outfit Builder, shop suggestions, Find Similar).
export default function AvatarPage({ onNavigate }: { onNavigate?: (page: Page) => void }) {
  const [status, setStatus] = useState<AvatarStatus | null>(null)
  const [error, setError] = useState("")
  const [avatarModel, setAvatarModel] = useBlobUrl()
  const [photoUrl, setPhotoUrl] = useBlobUrl()

  const [job, setJob] = useState<ActiveJob | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [showForm, setShowForm] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [consent, setConsent] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const loadAvatar = useCallback(async () => {
    try {
      setAvatarModel(await api.avatarModel())
      setPhotoUrl(await api.avatarPhoto())
    } catch {
      setAvatarModel(null)
      setPhotoUrl(null)
    }
  }, [setAvatarModel, setPhotoUrl])

  const refresh = useCallback(async () => {
    try {
      const next = await api.avatarStatus()
      setStatus(next)
      if (next.exists) await loadAvatar()
      else { setAvatarModel(null); setPhotoUrl(null) }
      if (next.job) setJob((previous) => previous ?? { id: next.job!.id, kind: next.job!.kind })
    } catch (loadError) {
      setError(message(loadError, "Could not load your avatar."))
    }
  }, [loadAvatar, setAvatarModel, setPhotoUrl])

  useEffect(() => { void refresh() }, [refresh])
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])

  // A generation takes one to two minutes: poll it, then show the result.
  useEffect(() => {
    if (!job) return
    const started = Date.now()
    setElapsed(0)
    const timer = window.setInterval(async () => {
      setElapsed(Math.round((Date.now() - started) / 1000))
      try {
        const state = await api.avatarJob(job.id)
        if (state.status === "running") return
        window.clearInterval(timer)
        setJob(null)
        if (state.status === "failed") setError(state.error || "The generation failed.")
        setStatus(await api.avatarStatus())
        if (job.kind === "avatar" && state.status === "done") {
          await loadAvatar()
          setShowForm(false); setFile(null); setPreview(null); setConsent(false)
        }
      } catch (pollError) {
        window.clearInterval(timer)
        setJob(null)
        setError(message(pollError, "Lost track of the generation."))
      }
    }, 3000)
    return () => window.clearInterval(timer)
  }, [job, loadAvatar])

  const choosePhoto = (chosen: File | undefined) => {
    if (!chosen) return
    setFile(chosen)
    setPreview(URL.createObjectURL(chosen))
  }

  const createAvatar = async () => {
    if (!file || !consent) return
    setError("")
    try {
      const started = await api.avatarCreate(file, consent)
      setJob({ id: started.job_id, kind: "avatar" })
    } catch (createError) {
      setError(message(createError, "Could not start the avatar."))
    }
  }

  const deleteAvatar = async () => {
    if (!window.confirm("Delete your 3D avatar, your photo and all your try-ons?")) return
    try {
      setStatus(await api.avatarDelete())
      setAvatarModel(null); setPhotoUrl(null)
    } catch (deleteError) {
      setError(message(deleteError, "Could not delete the avatar."))
    }
  }

  const hasAvatar = Boolean(status?.exists)
  const formVisible = showForm || (status !== null && !hasAvatar)
  const busy = job !== null
  const building = job?.kind === "avatar"

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">My 3D Avatar</h1>
        <p className="mt-1 text-sm text-[#8C8A82]">
          Your digital twin, made from one photo. It is used to try outfits on before you wear or buy them.
        </p>
      </div>

      {error && (
        <div className="flex items-start justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <span>{error}</span>
          <button type="button" onClick={() => setError("")} className="shrink-0 text-xs underline">Dismiss</button>
        </div>
      )}

      {status && !status.configured && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          The avatar service is not configured on the server. Add <code>FAL_KEY</code> to the server .env and restart the backend.
        </div>
      )}

      {job && (
        <div className="rounded-xl border border-[#556B2F]/30 bg-[#E8EDE0] px-4 py-3 text-sm text-[#1C1C1C]">
          <span className="mr-2 inline-block animate-pulse">✦</span>
          {building ? "Building your 3D avatar" : "A try-on is running"}… this takes one to two minutes ({elapsed}s). You can stay on this page.
        </div>
      )}

      <section className="grid gap-6 lg:grid-cols-[360px_1fr]">
        <div className="relative aspect-[3/4] overflow-hidden rounded-3xl bg-gradient-to-b from-[#2A2A28] to-[#1C1C1C]">
          {avatarModel && !building ? (
            <Viewer url={avatarModel} label="Your 3D avatar" />
          ) : preview ? (
            <img src={preview} alt="Your photo" className="h-full w-full object-cover" />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center text-white/55">
              <span className="text-5xl opacity-40">☺</span>
              <p className="text-sm">{status ? "Your avatar will appear here" : "Loading…"}</p>
            </div>
          )}
          {hasAvatar && !building && (
            <p className="pointer-events-none absolute inset-x-0 bottom-3 text-center text-[11px] text-white/45">
              Drag to turn your avatar
            </p>
          )}
        </div>

        <div className="space-y-5">
          {hasAvatar && !formVisible && (
            <>
              <div className="rounded-2xl border border-[#E2E0D8] bg-white p-6">
                <div className="flex items-center gap-4">
                  {photoUrl && <img src={photoUrl} alt="Your photo" className="h-20 w-16 shrink-0 rounded-lg object-cover object-top" />}
                  <div>
                    <p className="flex items-center gap-2 text-sm font-semibold text-[#1C1C1C]">
                      <span className="h-2 w-2 rounded-full bg-[#556B2F]" />
                      Your avatar is ready
                    </p>
                    <p className="mt-1 text-xs text-[#8C8A82]">
                      {status?.created_at ? `Created ${new Date(status.created_at).toLocaleDateString()}. ` : ""}
                      The photo is kept privately and only used for your try-ons.
                    </p>
                  </div>
                </div>
              </div>

              {onNavigate && (
                <div className="grid gap-3 sm:grid-cols-2">
                  <button
                    type="button"
                    onClick={() => onNavigate("outfit-builder")}
                    className="rounded-2xl border border-[#E2E0D8] bg-white p-5 text-left transition-colors hover:border-[#556B2F]"
                  >
                    <p className="text-sm font-semibold text-[#1C1C1C]">Try on an outfit</p>
                    <p className="mt-1 text-xs text-[#8C8A82]">Build a look from your wardrobe and see it on you.</p>
                  </button>
                  <button
                    type="button"
                    onClick={() => onNavigate("dashboard")}
                    className="rounded-2xl border border-[#E2E0D8] bg-white p-5 text-left transition-colors hover:border-[#556B2F]"
                  >
                    <p className="text-sm font-semibold text-[#1C1C1C]">Try on a shop piece</p>
                    <p className="mt-1 text-xs text-[#8C8A82]">See items from Tunisian shops on you before buying.</p>
                  </button>
                </div>
              )}

              <div className="flex flex-wrap items-center gap-2 border-t border-[#E2E0D8] pt-5">
                <button type="button" onClick={() => setShowForm(true)} disabled={busy}
                  className="rounded-lg border border-[#E2E0D8] bg-white px-4 py-2.5 text-sm font-semibold hover:bg-[#F0EFEA] disabled:opacity-40">
                  Use a new photo
                </button>
                <button type="button" onClick={() => void deleteAvatar()} disabled={busy}
                  className="rounded-lg px-4 py-2.5 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-40">
                  Delete my avatar and photo
                </button>
              </div>
            </>
          )}

          {formVisible && (
            <div className="space-y-5 rounded-2xl border border-[#E2E0D8] bg-white p-6">
              <div>
                <p className="flex items-center gap-2 text-sm font-semibold text-[#1C1C1C]">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#E8EDE0] text-xs text-[#556B2F]">1</span>
                  Choose your photo
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {PHOTO_TIPS.map((tip) => (
                    <span key={tip} className="rounded-full bg-[#F0EFEA] px-3 py-1 text-xs text-[#1C1C1C]">{tip}</span>
                  ))}
                </div>
                <p className="mt-2 text-xs text-[#8C8A82]">
                  The 3D model looks like your photo: the back and sides are inferred by the AI.
                </p>
                <button type="button" onClick={() => fileInput.current?.click()} disabled={busy}
                  className="mt-3 rounded-lg border border-[#E2E0D8] bg-white px-4 py-2.5 text-sm font-semibold hover:bg-[#F0EFEA] disabled:opacity-40">
                  {file ? "Choose another photo" : "Choose a photo"}
                </button>
                <input ref={fileInput} type="file" accept="image/*" hidden
                  onChange={(event) => { choosePhoto(event.target.files?.[0]); event.target.value = "" }} />
                {file && <span className="ml-3 text-xs text-[#8C8A82]">{file.name}</span>}
              </div>

              <div>
                <p className="flex items-center gap-2 text-sm font-semibold text-[#1C1C1C]">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#E8EDE0] text-xs text-[#556B2F]">2</span>
                  Your privacy
                </p>
                <label className="mt-3 flex items-start gap-2 rounded-lg bg-[#F0EFEA] p-3 text-xs text-[#1C1C1C]">
                  <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} className="mt-0.5 accent-[#556B2F]" />
                  <span>
                    I agree to send this photo to <b>fal.ai</b> (and the AI models it runs) to create my 3D avatar. DressMe keeps the photo and
                    the 3D models privately, in my account only, and I can delete everything at any time.
                  </span>
                </label>
              </div>

              <div>
                <p className="flex items-center gap-2 text-sm font-semibold text-[#1C1C1C]">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#E8EDE0] text-xs text-[#556B2F]">3</span>
                  Create it
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button type="button" onClick={() => void createAvatar()} disabled={!file || !consent || busy || status?.configured === false}
                    className="rounded-lg bg-[#556B2F] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#6B8A3A] disabled:opacity-40">
                    {building ? "Building…" : "Create my 3D avatar"}
                  </button>
                  {hasAvatar && (
                    <button type="button" onClick={() => { setShowForm(false); setFile(null); setPreview(null) }} disabled={busy}
                      className="rounded-lg border border-[#E2E0D8] bg-white px-4 py-2.5 text-sm font-semibold hover:bg-[#F0EFEA]">
                      Cancel
                    </button>
                  )}
                </div>
                <p className="mt-2 text-xs text-[#8C8A82]">Takes one to two minutes. It costs about $0.50 of AI credit.</p>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
