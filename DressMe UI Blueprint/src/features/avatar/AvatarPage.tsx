import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react"
import { api, asset } from "../../lib/api"
import { cap } from "../../lib/taxonomy"
import type { AvatarStatus, WardrobeItem } from "../../lib/types"
import { useWardrobe } from "../wardrobe/WardrobeProvider"

// three.js is only loaded when this page is opened.
const AvatarViewer = lazy(() => import("./AvatarViewer"))

// The try-on handles these wardrobe groups (shoes, bags and accessories are not supported).
const TRYON_GROUPS = ["Tops", "Outerwear", "Bottoms", "Dresses"]

type ActiveJob = { id: string; kind: "avatar" | "tryon"; itemId?: string }

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

function Viewer({ url, label }: { url: string; label: string }) {
  return (
    <Suspense fallback={<div className="grid h-full place-items-center text-sm text-[#8C8A82]">Loading viewer…</div>}>
      <AvatarViewer url={url} label={label} />
    </Suspense>
  )
}

export default function AvatarPage() {
  const { items } = useWardrobe()
  const [status, setStatus] = useState<AvatarStatus | null>(null)
  const [error, setError] = useState("")
  const [avatarModel, setAvatarModel] = useBlobUrl()
  const [photoUrl, setPhotoUrl] = useBlobUrl()
  const [resultModel, setResultModel] = useBlobUrl()
  const [resultImage, setResultImage] = useBlobUrl()
  const [resultItem, setResultItem] = useState<WardrobeItem | null>(null)
  const [resultView, setResultView] = useState<"3d" | "photo">("3d")

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

  const showTryOn = useCallback(async (item: WardrobeItem) => {
    const [model, image] = await Promise.allSettled([api.avatarTryOnModel(item.id), api.avatarTryOnImage(item.id)])
    setResultModel(model.status === "fulfilled" ? model.value : null)
    setResultImage(image.status === "fulfilled" ? image.value : null)
    setResultView(model.status === "fulfilled" ? "3d" : "photo")
    setResultItem(item)
  }, [setResultModel, setResultImage])

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
        const next = await api.avatarStatus()
        setStatus(next)
        if (job.kind === "avatar" && state.status === "done") {
          await loadAvatar()
          setResultItem(null); setResultModel(null); setResultImage(null)
          setShowForm(false); setFile(null); setPreview(null)
        } else if (job.kind === "tryon" && job.itemId) {
          const item = items.find((entry) => entry.id === job.itemId)
          if (item && next.tryons.some((entry) => entry.item_id === item.id)) await showTryOn(item)
        }
      } catch (pollError) {
        window.clearInterval(timer)
        setJob(null)
        setError(message(pollError, "Lost track of the generation."))
      }
    }, 3000)
    return () => window.clearInterval(timer)
  }, [job, items, loadAvatar, showTryOn, setResultModel, setResultImage])

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
      setAvatarModel(null); setPhotoUrl(null); setResultModel(null); setResultImage(null); setResultItem(null)
    } catch (deleteError) {
      setError(message(deleteError, "Could not delete the avatar."))
    }
  }

  const tryOn = async (item: WardrobeItem, redo = false) => {
    setError("")
    try {
      const started = await api.avatarTryOn(item.id, redo)
      if (started.cached || !started.job_id) await showTryOn(item)
      else setJob({ id: started.job_id, kind: "tryon", itemId: item.id })
    } catch (tryError) {
      setError(message(tryError, "The try-on failed."))
    }
  }

  const wearable = useMemo(() => items.filter((item) => TRYON_GROUPS.includes(item.category_group) && item.cutout_url), [items])
  const hasAvatar = Boolean(status?.exists)
  const formVisible = showForm || (status !== null && !hasAvatar)
  const busy = job !== null
  const triedIds = new Set(status?.tryons.map((entry) => entry.item_id))

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">My 3D Avatar</h1>
        <p className="mt-1 text-sm text-[#8C8A82]">A 3D model of you, made from one photo, to try your own clothes on</p>
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
          {job.kind === "avatar" ? "Building your 3D avatar" : "Dressing you in 3D"}… this takes one to two minutes ({elapsed}s). You can stay on this page.
        </div>
      )}

      <section className="grid gap-6 rounded-2xl border border-[#E2E0D8] bg-white p-6 md:grid-cols-[320px_1fr]">
        <div className="aspect-[3/4] overflow-hidden rounded-xl bg-[#F0EFEA]">
          {avatarModel && !(job?.kind === "avatar") ? (
            <Viewer url={avatarModel} label="Your 3D avatar" />
          ) : preview ? (
            <img src={preview} alt="Your photo" className="h-full w-full object-cover" />
          ) : (
            <div className="flex h-full items-center justify-center px-4 text-center text-sm text-[#8C8A82]">
              {status ? "No 3D avatar yet" : "Loading…"}
            </div>
          )}
        </div>

        <div className="space-y-4">
          {hasAvatar && !formVisible && (
            <>
              <p className="text-sm text-[#1C1C1C]">
                Your 3D avatar is ready{status?.created_at ? ` (created ${new Date(status.created_at).toLocaleDateString()})` : ""}. Turn it
                with your mouse, then pick a piece below to see it on you.
              </p>
              {photoUrl && (
                <div className="flex items-center gap-3 text-xs text-[#8C8A82]">
                  <img src={photoUrl} alt="Your photo" className="h-16 w-12 rounded object-cover" />
                  The photo it was made from (kept privately, used for try-ons)
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => setShowForm(true)} disabled={busy}
                  className="rounded-lg border border-[#E2E0D8] bg-white px-4 py-2.5 text-sm font-semibold hover:bg-[#F0EFEA] disabled:opacity-40">
                  Create a new one
                </button>
                <button type="button" onClick={() => void deleteAvatar()} disabled={busy}
                  className="rounded-lg border border-red-200 bg-white px-4 py-2.5 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-40">
                  Delete everything
                </button>
              </div>
            </>
          )}

          {formVisible && (
            <>
              <div>
                <p className="text-sm font-semibold text-[#1C1C1C]">Your photo</p>
                <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-[#8C8A82]">
                  <li>Full body, head to feet, standing straight, facing the camera, arms slightly away from the body.</li>
                  <li>Fitted clothes, good light, a plain background, nobody else in the photo.</li>
                  <li>The 3D model looks like the photo: the back and sides are inferred by the AI.</li>
                </ul>
                <button type="button" onClick={() => fileInput.current?.click()} disabled={busy}
                  className="mt-3 rounded-lg border border-[#E2E0D8] bg-white px-4 py-2.5 text-sm font-semibold hover:bg-[#F0EFEA] disabled:opacity-40">
                  {file ? "Choose another photo" : "Choose a photo"}
                </button>
                <input ref={fileInput} type="file" accept="image/*" hidden
                  onChange={(event) => { choosePhoto(event.target.files?.[0]); event.target.value = "" }} />
                {file && <span className="ml-3 text-xs text-[#8C8A82]">{file.name}</span>}
              </div>

              <label className="flex items-start gap-2 rounded-lg bg-[#F0EFEA] p-3 text-xs text-[#1C1C1C]">
                <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} className="mt-0.5 accent-[#556B2F]" />
                <span>
                  I agree to send this photo to <b>fal.ai</b> (and the AI models it runs) to create my 3D avatar. DressMe keeps the photo and
                  the 3D models privately, in my account only, and I can delete everything at any time.
                </span>
              </label>

              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => void createAvatar()} disabled={!file || !consent || busy || status?.configured === false}
                  className="rounded-lg bg-[#556B2F] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#6B8A3A] disabled:opacity-40">
                  {job?.kind === "avatar" ? "Building…" : "Create my 3D avatar"}
                </button>
                {hasAvatar && (
                  <button type="button" onClick={() => { setShowForm(false); setFile(null); setPreview(null) }} disabled={busy}
                    className="rounded-lg border border-[#E2E0D8] bg-white px-4 py-2.5 text-sm font-semibold hover:bg-[#F0EFEA]">
                    Cancel
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </section>

      {hasAvatar && (
        <section className="space-y-4">
          <div>
            <h2 className="font-display text-2xl text-[#1C1C1C]">Try it on in 3D</h2>
            <p className="mt-1 text-xs text-[#8C8A82]">
              Tops, jackets, bottoms and dresses from your wardrobe. The first time takes one to two minutes; a result you have already
              generated opens instantly.
            </p>
          </div>

          {resultItem && (
            <div className="grid gap-4 rounded-2xl border border-[#E2E0D8] bg-white p-4 sm:grid-cols-[320px_1fr]">
              <div className="aspect-[3/4] overflow-hidden rounded-xl bg-[#F0EFEA]">
                {resultView === "3d" && resultModel ? (
                  <Viewer url={resultModel} label={`You wearing ${resultItem.name} in 3D`} />
                ) : resultImage ? (
                  <img src={resultImage} alt={`You wearing ${resultItem.name}`} className="h-full w-full object-cover" />
                ) : null}
              </div>
              <div className="space-y-3">
                <p className="text-sm font-semibold text-[#1C1C1C]">{resultItem.name}</p>
                <div className="flex gap-1 rounded-lg border border-[#E2E0D8] p-0.5 text-xs font-semibold w-fit">
                  {(["3d", "photo"] as const).map((view) => (
                    <button key={view} type="button" disabled={(view === "3d" && !resultModel) || (view === "photo" && !resultImage)}
                      onClick={() => setResultView(view)}
                      className={`rounded-md px-3 py-1.5 disabled:opacity-30 ${resultView === view ? "bg-[#1C1C1C] text-white" : "hover:bg-[#F0EFEA]"}`}>
                      {view === "3d" ? "3D" : "Photo"}
                    </button>
                  ))}
                </div>
                {!resultModel && (
                  <p className="text-xs text-amber-800">The 3D conversion did not finish. The photo try-on is shown; press Redo to retry the 3D step.</p>
                )}
                <button type="button" onClick={() => void tryOn(resultItem, !resultModel ? false : true)} disabled={busy}
                  className="rounded-lg border border-[#E2E0D8] bg-white px-3 py-2 text-xs font-semibold hover:bg-[#F0EFEA] disabled:opacity-40"
                  title="Generate it again (uses credit)">
                  Redo
                </button>
              </div>
            </div>
          )}

          {wearable.length === 0 ? (
            <p className="text-sm text-[#8C8A82]">Add tops, jackets, bottoms or dresses to your wardrobe to try them on.</p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
              {wearable.map((item) => {
                const working = job?.kind === "tryon" && job.itemId === item.id
                return (
                  <button key={item.id} type="button" disabled={busy} onClick={() => void tryOn(item)}
                    className={`overflow-hidden rounded-xl border bg-white text-left transition-colors hover:border-[#556B2F] disabled:opacity-50 ${
                      resultItem?.id === item.id ? "border-[#556B2F]" : "border-[#E2E0D8]"
                    }`}>
                    <div className="aspect-[4/5] bg-[#F0EFEA]">
                      <img src={asset(item.cutout_url)} alt={item.name} loading="lazy" className="h-full w-full object-contain" />
                    </div>
                    <div className="p-2">
                      <p className="truncate text-xs font-semibold text-[#1C1C1C]">{item.name}</p>
                      <p className="truncate text-[10px] text-[#8C8A82]">
                        {working ? "Dressing you…" : triedIds.has(item.id) ? "✓ Tried - view" : `${cap(item.category)} · try on`}
                      </p>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </section>
      )}
    </div>
  )
}
