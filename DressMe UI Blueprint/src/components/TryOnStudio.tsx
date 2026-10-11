import { useEffect, useRef, useState } from "react"
import { AvatarCanvas } from "./AvatarViewer"
import {
  DEFAULT_DRESSED_URL,
  GARMENTS,
  generateAvatar,
  type GarmentId,
  type MpbParam,
} from "../lib/avatarApi"

type GenState = "idle" | "running" | "success" | "error"

export default function TryOnStudio({
  params,
  onBack,
  hasCustomized,
}: {
  params: Record<MpbParam, number>
  onBack: () => void
  hasCustomized: boolean
}) {
  const [selected, setSelected] = useState<GarmentId[]>(["tshirt", "trousers"])
  const [genState, setGenState] = useState<GenState>("idle")
  const [genError, setGenError] = useState<string | null>(null)
  const [url, setUrl] = useState<string>(DEFAULT_DRESSED_URL)
  const [isBaseModel, setIsBaseModel] = useState(true)
  const [lastJob, setLastJob] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    return () => abortRef.current?.abort()
  }, [])

  const toggle = (id: GarmentId) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((g) => g !== id) : [...prev, id]))
  }

  const onGenerate = async () => {
    if (genState === "running") return
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    const timer = window.setTimeout(() => controller.abort(), 320_000)
    setGenState("running")
    setGenError(null)
    try {
      const result = await generateAvatar(params, selected, controller.signal)
      setUrl(`${result.url}?v=${result.jobId}`)
      setLastJob(result.jobId)
      setIsBaseModel(false)
      setGenState("success")
    } catch (e) {
      const aborted = controller.signal.aborted
      setGenState("error")
      setGenError(
        aborted
          ? "Generation timed out after ~5 minutes. Check the backend console for the Blender log."
          : e instanceof Error
            ? e.message
            : "Generation failed for an unknown reason.",
      )
    } finally {
      window.clearTimeout(timer)
    }
  }

  const activeParams = (Object.entries(params) as [MpbParam, number][]).filter(
    ([, v]) => Math.abs(v - 0.5) > 0.001,
  )

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Try On Outfits</h1>
          <p className="text-[#8C8A82] text-sm mt-1">
            Pick garments and see them fitted to your avatar — drag to rotate, scroll to zoom
          </p>
        </div>
        <button
          onClick={onBack}
          className="shrink-0 bg-white hover:bg-[#E2E0D8] border border-[#E2E0D8] text-[#1C1C1C] text-sm font-semibold px-5 py-2.5 rounded-lg transition-colors"
        >
          ← Back to customization
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        <div className="space-y-6">
          <div className="bg-[#F0EFEA] rounded-xl p-6 space-y-4">
            <div>
              <h3 className="font-display text-lg font-medium text-[#1C1C1C]">Choose garments</h3>
              <p className="text-xs text-[#8C8A82] mt-0.5">
                Garments are generated to fit your current body shape — not just scaled
              </p>
            </div>
            <div className="space-y-2">
              {GARMENTS.map((g) => {
                const on = selected.includes(g.id)
                return (
                  <button
                    key={g.id}
                    onClick={() => toggle(g.id)}
                    className={`w-full flex items-center gap-3 p-3 rounded-lg border text-left transition-colors ${
                      on ? "bg-white border-[#556B2F]" : "bg-white/60 border-[#E2E0D8] hover:bg-white"
                    }`}
                  >
                    <span
                      className="w-8 h-8 rounded-md border border-[#E2E0D8] shrink-0"
                      style={{ backgroundColor: g.swatch }}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-semibold text-[#1C1C1C]">{g.label}</span>
                      <span className="block text-xs text-[#8C8A82]">{g.hint}</span>
                    </span>
                    <span
                      className={`w-5 h-5 rounded-full border flex items-center justify-center text-[10px] font-bold ${
                        on ? "bg-[#556B2F] border-[#556B2F] text-white" : "border-[#C9C7BE] text-transparent"
                      }`}
                    >
                      ✓
                    </span>
                  </button>
                )
              })}
            </div>

            <div className="bg-white rounded-lg px-4 py-4 space-y-3 border border-[#E2E0D8]">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-[#1C1C1C]">Generate try-on</p>
                  <p className="text-xs text-[#8C8A82]">
                    {selected.length ? selected.join(" + ") : "Body only (no garments)"}
                  </p>
                </div>
                <button
                  onClick={onGenerate}
                  disabled={genState === "running"}
                  className="bg-[#556B2F] hover:bg-[#6B8A3A] text-white text-sm font-semibold px-6 py-2.5 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
                >
                  {genState === "running" ? "Dressing…" : "Generate"}
                </button>
              </div>
              <p className="text-xs text-[#8C8A82]">
                Body:{" "}
                {activeParams.length
                  ? activeParams.map(([k, v]) => `${k} ${v.toFixed(2)}`).join(", ")
                  : "neutral (all parameters 0.50)"}
                {hasCustomized ? "" : " — customize the body first for a personal fit"}
              </p>
              {genState === "running" && (
                <p className="text-xs text-[#556B2F]">Blender is fitting the garments… (~10–20 s)</p>
              )}
              {genState === "success" && (
                <p className="text-xs text-[#556B2F]">
                  Done — outfit regenerated to fit your body (job {lastJob}).
                </p>
              )}
              {genState === "error" && genError && (
                <div className="bg-[#F5E0E0] text-[#8A2E2E] text-xs rounded-lg px-3 py-2.5">{genError}</div>
              )}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="relative">
            <AvatarCanvas url={url} />
            {genState === "running" && (
              <div className="absolute inset-0 rounded-xl bg-[#F0EFEA]/70 flex items-center justify-center">
                <span className="text-sm font-semibold text-[#556B2F]">Dressing your avatar…</span>
              </div>
            )}
          </div>
          <div className="bg-[#F0EFEA] rounded-xl px-5 py-4">
            <p className="text-xs text-[#8C8A82]">
              {isBaseModel
                ? "Showing the bundled base outfit. Press Generate to fit garments to your body shape."
                : "Showing your generated outfit. Change the selection and generate again to compare."}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
