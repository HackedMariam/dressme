import { useEffect, useRef, useState } from "react"
import { AvatarCanvas } from "./AvatarViewer"
import {
  DEFAULT_DRESSED_URL,
  checkAvatarBackend,
  generateAvatar,
  type BodyTargets,
  type DetailTargets,
  type GenerateResult,
  type Health,
} from "../lib/avatarApi"
import {
  SLOT_LABELS,
  SLOT_ORDER,
  clearSlot,
  garmentById,
  garmentsForSlot,
  selectionLabel,
  toggleGarment,
  wardrobeIdsForSelection,
  type GarmentId,
} from "../lib/garments"
import type { SavedLook } from "../lib/looks"
import { wardrobeItems } from "../lib/wardrobe"

type GenState = "idle" | "running" | "success" | "error"

function describeBody(params: BodyTargets): string {
  const active = (Object.entries(params) as [string, number][]).filter(
    ([, value]) => Math.abs(value - 0.5) > 0.001,
  )
  return active.length ? active.map(([k, v]) => `${k} ${v.toFixed(2)}`).join(", ") : "neutral (all 0.50)"
}

function describeOutfit(ids: GarmentId[]): string {
  return ids.length ? ids.map((id) => garmentById(id)?.label ?? id).join(" + ") : "body only"
}

export default function TryOnStudio({
  params,
  details,
  selection,
  onSelectionChange,
  savedLooks,
  onSaveLook,
  onBack,
  hasCustomized,
}: {
  params: BodyTargets
  details: DetailTargets
  selection: GarmentId[]
  onSelectionChange: (next: GarmentId[]) => void
  savedLooks: SavedLook[]
  onSaveLook: (look: Omit<SavedLook, "id" | "createdAt">) => void
  onBack: () => void
  hasCustomized: boolean
}) {
  const [genState, setGenState] = useState<GenState>("idle")
  const [genError, setGenError] = useState<string | null>(null)
  const [url, setUrl] = useState<string>(DEFAULT_DRESSED_URL)
  const [lastResult, setLastResult] = useState<GenerateResult | null>(null)
  const [history, setHistory] = useState<GenerateResult[]>([])
  const [compare, setCompare] = useState(false)
  const [health, setHealth] = useState<Health | null>(null)
  const [healthError, setHealthError] = useState<string | null>(null)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    let active = true
    checkAvatarBackend()
      .then((result) => {
        if (active) setHealth(result)
      })
      .catch(() => {
        if (active) setHealthError("Backend offline")
      })
    return () => {
      active = false
      abortRef.current?.abort()
    }
  }, [])

  const previous = history[1] ?? null
  const displayUrl = compare && previous ? `${previous.url}?v=${previous.jobId}` : url
  const backendReady = Boolean(
    health?.blenderExists && health?.blendExists && health?.dressedScriptExists,
  )

  const onGenerate = async () => {
    if (genState === "running") return
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    const timer = window.setTimeout(() => controller.abort(), 320_000)
    setGenState("running")
    setGenError(null)
    setSaveMessage(null)
    try {
      const result = await generateAvatar(params, selection, controller.signal, details)
      setUrl(`${result.url}?v=${result.jobId}`)
      setLastResult(result)
      setHistory((prev) => [result, ...prev].slice(0, 5))
      setCompare(false)
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

  const onSave = () => {
    onSaveLook({
      label: selectionLabel(selection),
      garmentIds: selection,
      wardrobeIds: wardrobeIdsForSelection(selection),
    })
    setSaveMessage("Look saved — open Outfit Studio to reload it.")
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Try On Outfits</h1>
          <p className="text-[#8C8A82] text-sm mt-1">
            Pick one piece per slot, then generate a body-fitted try-on — drag to rotate, scroll to zoom
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
          <div className="bg-[#F0EFEA] rounded-xl p-6 space-y-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="font-display text-lg font-medium text-[#1C1C1C]">Choose what to try on</h3>
                <p className="text-xs text-[#8C8A82] mt-0.5">
                  One item per slot. A dress replaces the top and bottom; outerwear layers over a top.
                </p>
              </div>
              <span
                className={`text-[10px] font-semibold px-2.5 py-1 rounded-full ${
                  backendReady
                    ? "bg-[#E8EDE0] text-[#556B2F]"
                    : health
                      ? "bg-[#F5EDDC] text-[#7A5B1E]"
                      : healthError
                        ? "bg-[#F5E0E0] text-[#8A2E2E]"
                        : "bg-[#E2E0D8] text-[#8C8A82]"
                }`}
              >
                {backendReady
                  ? "Backend ready"
                  : health
                    ? "Backend incomplete"
                    : healthError
                      ? "Backend offline"
                      : "Checking backend…"}
              </span>
            </div>

            {SLOT_ORDER.map((slot) => {
              const options = garmentsForSlot(slot)
              const activeInSlot = selection.filter((id) => garmentById(id)?.slot === slot)
              return (
                <div key={slot} className="space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest">
                      {SLOT_LABELS[slot]}
                    </p>
                    <button
                      type="button"
                      onClick={() => onSelectionChange(clearSlot(selection, slot))}
                      disabled={!activeInSlot.length}
                      className="text-[11px] font-semibold text-[#8C8A82] hover:text-[#1C1C1C] disabled:opacity-30 disabled:hover:text-[#8C8A82]"
                    >
                      None
                    </button>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    {options.map((garment) => {
                      const on = selection.includes(garment.id)
                      return (
                        <button
                          key={garment.id}
                          type="button"
                          onClick={() => onSelectionChange(toggleGarment(selection, garment.id))}
                          className={`flex items-center gap-3 p-3 rounded-lg border text-left transition-colors ${
                            on ? "bg-white border-[#556B2F]" : "bg-white/60 border-[#E2E0D8] hover:bg-white"
                          }`}
                        >
                          <span
                            className="w-8 h-8 rounded-md border border-[#E2E0D8] shrink-0"
                            style={{ backgroundColor: garment.swatch }}
                          />
                          <span className="min-w-0 flex-1">
                            <span className="block text-sm font-semibold text-[#1C1C1C]">{garment.label}</span>
                            <span className="block text-[11px] text-[#8C8A82] leading-tight">{garment.hint}</span>
                          </span>
                          <span
                            className={`w-5 h-5 rounded-full border flex items-center justify-center text-[10px] font-bold shrink-0 ${
                              on ? "bg-[#556B2F] border-[#556B2F] text-white" : "border-[#C9C7BE] text-transparent"
                            }`}
                          >
                            ✓
                          </span>
                        </button>
                      )
                    })}
                  </div>
                </div>
              )
            })}

            <div className="border-t border-[#E2E0D8] pt-4 space-y-2">
              <div>
                <p className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest">From your wardrobe</p>
                <p className="text-[11px] text-[#8C8A82] mt-0.5">Tap an owned item to wear its closest try-on piece.</p>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {wardrobeItems.map((item) => {
                  const garment = garmentById(item.garmentId)
                  const on = selection.includes(item.garmentId)
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => onSelectionChange(toggleGarment(selection, item.garmentId))}
                      className={`flex items-center gap-2.5 p-2 rounded-lg border text-left transition-colors ${
                        on ? "bg-white border-[#556B2F]" : "bg-white/60 border-[#E2E0D8] hover:bg-white"
                      }`}
                    >
                      <img
                        src={item.img}
                        alt={item.name}
                        className="w-10 h-12 rounded object-cover shrink-0 bg-[#E2E0D8]"
                      />
                      <span className="min-w-0">
                        <span className="block text-xs font-semibold text-[#1C1C1C] truncate">{item.name}</span>
                        <span className="block text-[10px] text-[#8C8A82]">
                          {garment?.label ?? "Try-on piece"} · {item.color}
                        </span>
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>

            {savedLooks.length > 0 && (
              <div className="border-t border-[#E2E0D8] pt-4 space-y-2">
                <p className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest">Saved looks</p>
                {savedLooks.slice(0, 4).map((look) => (
                  <button
                    key={look.id}
                    type="button"
                    onClick={() => onSelectionChange(look.garmentIds)}
                    className="w-full flex items-center justify-between gap-3 px-3 py-2 rounded-lg bg-white/70 border border-[#E2E0D8] hover:bg-white transition-colors text-left"
                  >
                    <span className="text-xs font-semibold text-[#1C1C1C] truncate">{look.label}</span>
                    <span className="text-[10px] text-[#8C8A82] shrink-0">
                      {new Date(look.createdAt).toLocaleDateString()}
                    </span>
                  </button>
                ))}
              </div>
            )}

            <div className="bg-white rounded-lg px-4 py-4 space-y-3 border border-[#E2E0D8]">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-[#1C1C1C]">Generate try-on</p>
                  <p className="text-xs text-[#8C8A82] truncate">{describeOutfit(selection)}</p>
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
                Body: {describeBody(params)}
                {hasCustomized ? "" : " — customize the body first for a personal fit"}
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={onSave}
                  disabled={!selection.length}
                  className="text-xs font-semibold border border-[#E2E0D8] rounded-lg px-3 py-1.5 text-[#1C1C1C] hover:bg-[#F0EFEA] disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Save look
                </button>
                {lastResult && (
                  <a
                    href={displayUrl}
                    download
                    className="text-xs font-semibold border border-[#E2E0D8] rounded-lg px-3 py-1.5 text-[#1C1C1C] hover:bg-[#F0EFEA]"
                  >
                    Download GLB
                  </a>
                )}
              </div>
              {genState === "running" && (
                <p className="text-xs text-[#556B2F]">Blender is fitting the garments… (~10–40 s)</p>
              )}
              {genState === "success" && (
                <p className="text-xs text-[#556B2F]">
                  Done — outfit regenerated to fit your body (job {lastResult?.jobId}).
                </p>
              )}
              {saveMessage && <p className="text-xs text-[#556B2F]">{saveMessage}</p>}
              {healthError && (
                <p className="text-xs text-[#8A2E2E]">
                  {healthError}. Start it with{" "}
                  <code className="font-mono">cd backend && uvicorn main:app --host 127.0.0.1 --port 8000</code>.
                </p>
              )}
              {health && !backendReady && (
                <p className="text-xs text-[#7A5B1E]">
                  The backend is running but Blender or avatar.blend is missing. Check backend/README.md for the
                  expected paths.
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
            <AvatarCanvas url={displayUrl} />
            {genState === "running" && (
              <div className="absolute inset-0 rounded-xl bg-[#F0EFEA]/70 flex items-center justify-center">
                <span className="text-sm font-semibold text-[#556B2F]">Dressing your avatar…</span>
              </div>
            )}
            {compare && previous && (
              <div className="absolute top-3 left-3 bg-[#1C1C1C]/80 text-white text-[10px] font-semibold px-2.5 py-1 rounded-full">
                Previous look
              </div>
            )}
          </div>

          <div className="bg-[#F0EFEA] rounded-xl px-5 py-4 space-y-3">
            <p className="text-xs text-[#8C8A82]">
              {lastResult
                ? "Showing your generated outfit. Change the selection and generate again to compare."
                : "Showing the bundled base outfit. Press Generate to fit garments to your body shape."}
            </p>
            {lastResult?.metrics && Object.keys(lastResult.metrics).length > 0 && (
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="bg-white rounded-lg px-2 py-2">
                  <p className="text-[10px] text-[#8C8A82] uppercase tracking-wide">Shoulder/hip</p>
                  <p className="text-sm font-semibold text-[#1C1C1C] tabular-nums">
                    {Number(lastResult.metrics.shoulderToHip ?? 0).toFixed(2)}
                  </p>
                </div>
                <div className="bg-white rounded-lg px-2 py-2">
                  <p className="text-[10px] text-[#8C8A82] uppercase tracking-wide">Torso/leg</p>
                  <p className="text-sm font-semibold text-[#1C1C1C] tabular-nums">
                    {Number(lastResult.metrics.torsoToLeg ?? 0).toFixed(2)}
                  </p>
                </div>
                <div className="bg-white rounded-lg px-2 py-2">
                  <p className="text-[10px] text-[#8C8A82] uppercase tracking-wide">Height</p>
                  <p className="text-sm font-semibold text-[#1C1C1C] tabular-nums">
                    {lastResult.metrics.heightMeters
                      ? `${Number(lastResult.metrics.heightMeters).toFixed(2)} m`
                      : "—"}
                  </p>
                </div>
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setCompare((value) => !value)}
                disabled={!previous}
                className="text-xs font-semibold border border-[#E2E0D8] rounded-lg px-3 py-1.5 text-[#1C1C1C] hover:bg-white disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {compare ? "Show latest" : "Compare previous"}
              </button>
              <button
                type="button"
                onClick={() => onSelectionChange(lastResult?.outfit ?? [])}
                disabled={!lastResult}
                className="text-xs font-semibold border border-[#E2E0D8] rounded-lg px-3 py-1.5 text-[#1C1C1C] hover:bg-white disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Reuse last selection
              </button>
            </div>
          </div>

          {history.length > 0 && (
            <div className="bg-[#F0EFEA] rounded-xl px-5 py-4 space-y-2">
              <p className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest">Recent try-ons</p>
              {history.map((item, index) => (
                <div
                  key={`${item.jobId}-${index}`}
                  className="flex items-center justify-between gap-2 bg-white rounded-lg px-3 py-2"
                >
                  <button
                    type="button"
                    onClick={() => {
                      setUrl(`${item.url}?v=${item.jobId}`)
                      setLastResult(item)
                      setCompare(false)
                    }}
                    className="text-left min-w-0 flex-1"
                  >
                    <span className="block text-xs font-semibold text-[#1C1C1C] truncate">
                      {describeOutfit(item.outfit)}
                    </span>
                    <span className="block text-[10px] text-[#8C8A82]">
                      {item.elapsedSeconds.toFixed(1)}s · {item.metrics?.heightMeters
                        ? `${Number(item.metrics.heightMeters).toFixed(2)} m`
                        : "height n/a"}
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => onSelectionChange(item.outfit)}
                    className="text-[10px] font-semibold text-[#556B2F] hover:underline shrink-0"
                  >
                    Use selection
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
