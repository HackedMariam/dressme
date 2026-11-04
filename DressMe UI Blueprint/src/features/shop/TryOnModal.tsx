import { useEffect, useRef, useState } from "react"
import { ApiError, api } from "../../lib/api"

export type Garment = { file?: File; imageUrl?: string }

type Phase = "ready" | "working" | "done" | "failed"

const POLL_MS = 3000

// Virtual try-on of a piece the user does not own: their avatar photo wearing a shop item (about $0.075 on fal.ai).
// Nothing is sent until the user presses the start button, because every try-on costs money.
export default function TryOnModal({
  garment,
  group,
  label,
  onClose,
  onOpenAvatar,
}: {
  garment: Garment
  group: string
  label: string
  onClose: () => void
  onOpenAvatar?: () => void
}) {
  const [phase, setPhase] = useState<Phase>("ready")
  const [error, setError] = useState("")
  const [needsAvatar, setNeedsAvatar] = useState(false)
  const [preview, setPreview] = useState("")
  const [result, setResult] = useState("")
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  useEffect(() => {
    if (garment.file) {
      const url = URL.createObjectURL(garment.file)
      setPreview(url)
      return () => URL.revokeObjectURL(url)
    }
    setPreview(garment.imageUrl ?? "")
  }, [garment])

  useEffect(() => {
    return () => {
      if (result) URL.revokeObjectURL(result)
    }
  }, [result])

  const fail = (message: string) => {
    if (!alive.current) return
    setError(message)
    setPhase("failed")
  }

  const start = async () => {
    setPhase("working")
    setError("")
    setNeedsAvatar(false)
    try {
      const { tryon_id, job_id } = await api.avatarTryOnGarment(garment, group)
      while (alive.current) {
        await new Promise((resolve) => setTimeout(resolve, POLL_MS))
        if (!alive.current) return
        const job = await api.avatarJob(job_id)
        if (job.status === "failed") return fail(job.error || "The try-on failed. Please try again.")
        if (job.status === "done") {
          const blob = await api.avatarTryOnImage(tryon_id)
          if (!alive.current) return
          setResult(URL.createObjectURL(blob))
          setPhase("done")
          return
        }
      }
    } catch (tryError) {
      if (tryError instanceof ApiError && tryError.status === 409) setNeedsAvatar(true)
      fail(tryError instanceof Error ? tryError.message : "The try-on failed.")
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Virtual try-on"
      onClick={(event) => event.target === event.currentTarget && phase !== "working" && onClose()}
    >
      <div className="max-h-full w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-6 shadow-xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="font-display text-xl font-semibold text-[#1C1C1C]">Virtual try-on</h2>
            <p className="mt-0.5 text-xs text-[#8C8A82]">{label}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={phase === "working"}
            className="text-sm text-[#8C8A82] hover:text-[#1C1C1C] disabled:opacity-40"
          >
            Close
          </button>
        </div>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div className="flex aspect-[3/4] items-center justify-center overflow-hidden rounded-xl bg-[#F0EFEA]">
            {preview ? (
              <img src={preview} alt={label} referrerPolicy="no-referrer" className="h-full w-full object-contain" />
            ) : null}
          </div>
          <div className="flex aspect-[3/4] items-center justify-center overflow-hidden rounded-xl bg-[#F0EFEA] text-center">
            {phase === "done" && result ? (
              <img src={result} alt="You wearing this piece" className="h-full w-full object-contain" />
            ) : phase === "working" ? (
              <div className="px-4">
                <div className="mx-auto h-9 w-9 animate-spin rounded-full border-4 border-[#E2E0D8] border-t-[#556B2F]" />
                <p className="mt-3 text-sm font-medium text-[#1C1C1C]">Dressing your avatar...</p>
                <p className="mt-1 text-xs text-[#8C8A82]">Usually under a minute. Keep this window open.</p>
              </div>
            ) : (
              <p className="px-4 text-sm text-[#8C8A82]">Your try-on will appear here.</p>
            )}
          </div>
        </div>

        {error && (
          <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
            {needsAvatar && onOpenAvatar && (
              <button type="button" onClick={onOpenAvatar} className="ml-2 font-semibold underline">
                Create my avatar
              </button>
            )}
          </div>
        )}

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <p className="max-w-sm text-xs text-[#8C8A82]">
            Your private avatar photo and this garment image are sent to fal.ai. Cost: about $0.08.
          </p>
          {phase !== "done" && (
            <button
              type="button"
              disabled={phase === "working"}
              onClick={() => void start()}
              className="rounded-lg bg-[#556B2F] px-5 py-2.5 text-xs font-semibold text-white hover:bg-[#6B8A3A] disabled:opacity-40"
            >
              {phase === "failed" ? "Try again" : "Start the try-on"}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
