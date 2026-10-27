import { useEffect, useMemo, useRef, useState } from "react"
import { AvatarCanvas } from "./AvatarViewer"
import {
  DEFAULT_DRESSED_URL,
  checkAvatarBackend,
  generateAvatar,
  versionedUrl,
  type AvatarSnapshot,
  type BodyTargets,
  type DetailTargets,
  type GenerateResult,
  type Health,
} from "../lib/avatarApi"
import {
  SLOT_LABELS,
  SLOT_ORDER,
  garmentById,
  type GarmentSlot,
} from "../lib/garments"
import type { SavedLook } from "../lib/looks"
import {
  clearTryOnSlot,
  resolveTryOnItem,
  toggleTryOnItem,
  tryOnItemsFromSnapshots,
  tryOnLabel,
  tryOnPayload,
  tryOnSnapshots,
  type TryOnItem,
} from "../lib/tryon"
import { useAuth } from "../features/auth/AuthProvider"
import { useWardrobeItems } from "../features/wardrobe/useWardrobeItems"

type GenState = "idle" | "running" | "success" | "error"

function describeBody(params: BodyTargets): string {
  const active = (Object.entries(params) as [string, number][]).filter(
    ([, value]) => Math.abs(value - 0.5) > 0.001,
  )
  return active.length ? active.map(([k, v]) => `${k} ${v.toFixed(2)}`).join(", ") : "neutral (all 0.50)"
}

function describeOutfit(items: TryOnItem[]): string {
  return items.length ? items.map((item) => item.label).join(" + ") : "body only"
}

function ItemThumb({ item }: { item: TryOnItem }) {
  if (item.cutoutUrl) {
    return (
      <img
        src={item.cutoutUrl}
        alt={item.label}
        className="w-10 h-12 rounded object-contain shrink-0 bg-[#E2E0D8]"
      />
    )
  }
  return (
    <span
      className="w-10 h-12 rounded border border-[#E2E0D8] shrink-0"
      style={{ backgroundColor: item.colorHex }}
    />
  )
}

export default function TryOnStudio({
  params,
  details,
  heightCm,
  selection,
  onSelectionChange,
  savedLooks,
  onSaveLook,
  onBack,
  hasCustomized,
  initialAvatar,
  onAvatarSaved,
}: {
  params: BodyTargets
  details: DetailTargets
  heightCm: number
  selection: TryOnItem[]
  onSelectionChange: (next: TryOnItem[]) => void
  savedLooks: SavedLook[]
  onSaveLook: (look: Omit<SavedLook, "id" | "createdAt">) => void
  onBack: () => void
  hasCustomized: boolean
  initialAvatar?: AvatarSnapshot | null
  onAvatarSaved?: () => void
}) {
  const { user } = useAuth()
  const { items: wardrobeItems, loading: wardrobeLoading, error: wardrobeError } = useWardrobeItems(user?.id)
  const [genState, setGenState] = useState<GenState>("idle")
  const [genError, setGenError] = useState<string | null>(null)
  const [url, setUrl] = useState<string>(initialAvatar?.url ?? DEFAULT_DRESSED_URL)
  const [lastResult, setLastResult] = useState<GenerateResult | null>(null)
  const [history, setHistory] = useState<GenerateResult[]>([])
  const [compare, setCompare] = useState(false)
  const [health, setHealth] = useState<Health | null>(null)
  const [healthError, setHealthError] = useState<string | null>(null)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (initialAvatar?.url) setUrl(initialAvatar.url)
  }, [initialAvatar?.url])

  useEffect(() => {
    if (genState !== "running") return
    const warnBeforeLeaving = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = "Your avatar is still being generated."
    }
    window.addEventListener("beforeunload", warnBeforeLeaving)
    return () => window.removeEventListener("beforeunload", warnBeforeLeaving)
  }, [genState])

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

  const available = useMemo(
    () =>
      wardrobeItems.flatMap((item) => {
        const resolved = resolveTryOnItem(item)
        return resolved ? [resolved] : []
      }),
    [wardrobeItems],
  )
  const unsupportedCount = wardrobeItems.length - available.length

  useEffect(() => {
    if (wardrobeLoading || selection.length === 0) return
    const valid = new Set(available.map((item) => item.wardrobeId))
    if (selection.every((item) => valid.has(item.wardrobeId))) return
    onSelectionChange(selection.filter((item) => valid.has(item.wardrobeId)))
  }, [available, onSelectionChange, selection, wardrobeLoading])

  const previous = history[1] ?? null
  const displayUrl = compare && previous ? versionedUrl(previous.url, previous.jobId) : url
  const backendReady = Boolean(
    health?.blenderExists && health?.blendExists && health?.dressedScriptExists,
  )

  const onGenerate = async () => {
    if (genState === "running" || selection.length === 0) return
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    const timer = window.setTimeout(() => controller.abort(), 320_000)
    setGenState("running")
    setGenError(null)
    setSaveMessage(null)
    try {
      const result = await generateAvatar(
        params,
        selection.map((item) => item.templateId),
        controller.signal,
        details,
        {
          wardrobeItemIds: selection.map((item) => item.wardrobeId),
          wardrobeItems: tryOnPayload(selection),
          heightCm,
        },
      )
      setUrl(versionedUrl(result.url, result.jobId))
      setLastResult(result)
      setHistory((prev) => [result, ...prev].slice(0, 5))
      setCompare(false)
      setGenState("success")
      if (result.saved !== false) onAvatarSaved?.()
      if (result.saved === false) {
        setSaveMessage(result.saveError || "Generated, but the avatar could not be saved.")
      }
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
      label: tryOnLabel(selection),
      garmentIds: selection.map((item) => item.templateId),
      wardrobeIds: selection.map((item) => item.wardrobeId),
      items: tryOnSnapshots(selection),
    })
    setSaveMessage("Look saved — open Outfit Studio to reload it.")
  }

  const loadSavedLook = (look: SavedLook) => {
    if (look.items?.length) {
      onSelectionChange(tryOnItemsFromSnapshots(look.items))
      return
    }
    const fromWardrobe = available.filter((item) => look.garmentIds.includes(item.templateId))
    onSelectionChange(fromWardrobe.slice(0, 5))
  }

  const reuseResult = (result: GenerateResult) => {
    if (result.items?.length) {
      onSelectionChange(tryOnItemsFromSnapshots(result.items))
      return
    }
    onSelectionChange(available.filter((item) => result.outfit.includes(item.templateId)))
  }

  const renderSlot = (slot: GarmentSlot) => {
    const options = available.filter((item) => item.slot === slot)
    const activeInSlot = selection.filter((item) => item.slot === slot)

    return (
      <div key={slot} className="space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest">
            {SLOT_LABELS[slot]}
          </p>
          <button
            type="button"
            onClick={() => onSelectionChange(clearTryOnSlot(selection, slot))}
            disabled={!activeInSlot.length}
            className="text-[11px] font-semibold text-[#8C8A82] hover:text-[#1C1C1C] disabled:opacity-30 disabled:hover:text-[#8C8A82]"
          >
            None
          </button>
        </div>
        {options.length === 0 ? (
          <p className="text-[11px] text-[#8C8A82] rounded-lg border border-dashed border-[#E2E0D8] px-3 py-2">
            No match in your wardrobe for this slot.
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            {options.map((item) => {
              const on = selection.some((entry) => entry.wardrobeId === item.wardrobeId)
              const meta = garmentById(item.templateId)
              return (
                <button
                  key={`${item.wardrobeId}-${item.templateId}`}
                  type="button"
                  onClick={() => onSelectionChange(toggleTryOnItem(selection, item))}
                  className={`flex items-center gap-2.5 p-2 rounded-lg border text-left transition-colors ${
                    on ? "bg-white border-[#556B2F]" : "bg-white/60 border-[#E2E0D8] hover:bg-white"
                  }`}
                >
                  <ItemThumb item={item} />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5">
                      <span className="block text-xs font-semibold text-[#1C1C1C] truncate">{item.label}</span>
                      {item.meshUrl && (
                        <span className="shrink-0 rounded-full bg-[#E8EDE0] px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-[#556B2F]">
                          3D
                        </span>
                      )}
                    </span>
                    <span className="block text-[10px] text-[#8C8A82] truncate">
                      {meta?.label ?? item.templateId} · {item.colorHex}
                    </span>
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
        )}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Try On Outfits</h1>
          <p className="text-[#8C8A82] text-sm mt-1">
            Pick pieces from your wardrobe, then generate a body-fitted try-on — drag to rotate, scroll to zoom
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
                  Items come from your wardrobe. One item per slot; a dress replaces the top and bottom.
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

            {wardrobeLoading && (
              <p className="text-xs text-[#8C8A82]">Loading your wardrobe…</p>
            )}
            {wardrobeError && (
              <div className="bg-[#F5E0E0] text-[#8A2E2E] text-xs rounded-lg px-3 py-2.5">
                Could not load your wardrobe: {wardrobeError}
              </div>
            )}
            {!wardrobeLoading && !wardrobeError && wardrobeItems.length === 0 && (
              <p className="text-xs text-[#8C8A82]">
                Your wardrobe is empty. Add clothes in My Wardrobe before trying them on.
              </p>
            )}

            {SLOT_ORDER.map(renderSlot)}

            {unsupportedCount > 0 && (
              <p className="text-[11px] text-[#8C8A82] border-t border-[#E2E0D8] pt-3">
                {unsupportedCount} item{unsupportedCount === 1 ? "" : "s"} have no 3D try-on template
                (bags, accessories, shorts, skirts…).
              </p>
            )}

            {savedLooks.length > 0 && (
              <div className="border-t border-[#E2E0D8] pt-4 space-y-2">
                <p className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest">Saved looks</p>
                {savedLooks.slice(0, 4).map((look) => (
                  <button
                    key={look.id}
                    type="button"
                    onClick={() => loadSavedLook(look)}
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
                  disabled={genState === "running" || selection.length === 0}
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
                  {lastResult?.saved ? " Saved as your last avatar." : ""}
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
                : initialAvatar
                  ? "Showing your last saved avatar. Generate to update it with the current selection."
                  : "Showing the bundled base outfit. Press Generate to fit wardrobe items to your body shape."}
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
                onClick={() => lastResult && reuseResult(lastResult)}
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
                      setUrl(versionedUrl(item.url, item.jobId))
                      setLastResult(item)
                      setCompare(false)
                    }}
                    className="text-left min-w-0 flex-1"
                  >
                    <span className="block text-xs font-semibold text-[#1C1C1C] truncate">
                      {item.items?.length
                        ? item.items.map((entry) => entry.label).join(" + ")
                        : describeOutfit(available.filter((entry) => item.outfit.includes(entry.templateId)))}
                    </span>
                    <span className="block text-[10px] text-[#8C8A82]">
                      {item.elapsedSeconds.toFixed(1)}s · {item.metrics?.heightMeters
                        ? `${Number(item.metrics.heightMeters).toFixed(2)} m`
                        : "height n/a"}
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => reuseResult(item)}
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
