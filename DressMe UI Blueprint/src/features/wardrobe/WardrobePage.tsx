import { lazy, Suspense, useMemo, useRef, useState } from "react"
import { api, asset } from "../../lib/api"
import { COLORS, TAXONOMY, cap, formatDate, seasonLabel } from "../../lib/taxonomy"
import type { SkippedItem, WardrobeItem } from "../../lib/types"
import { useSpeech } from "../../lib/useSpeech"
import ItemDrawer from "./ItemDrawer"
import LiveScan from "./LiveScan"
import { useWardrobe } from "./WardrobeProvider"

const Wardrobe3D = lazy(() => import("./Wardrobe3D"))

// A photo (or one garment of it) the server did not save, waiting for the user to confirm or dismiss.
interface HeldPhoto extends SkippedItem {
  id: string
  file: File
  preview: string
  multi: boolean
}

interface UploadJob {
  id: string
  preview: string
  error?: string
}

function itemHaystack(item: WardrobeItem) {
  return [
    item.name,
    item.color_name,
    item.category,
    item.category_group,
    item.style,
    item.pattern,
    item.material,
    ...(item.seasons ?? []),
    ...(item.occasions ?? []),
    ...(item.tags ?? []),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase()
}

function ItemCard({
  item,
  onSelect,
}: {
  item: WardrobeItem
  onSelect: (id: string) => void
}) {
  const confidence = item.confidence ?? 0
  const lowConfidence = confidence < 0.6
  return (
    <button
      type="button"
      onClick={() => onSelect(item.id)}
      className="group overflow-hidden rounded-xl border border-[#E2E0D8] bg-white text-left transition-colors hover:border-[#556B2F]"
    >
      <div className="relative aspect-[4/5] overflow-hidden bg-[#F0EFEA]">
        {item.cutout_url ? (
          <img
            src={asset(item.cutout_url)}
            alt={item.name}
            loading="lazy"
            className="h-full w-full object-contain transition-transform duration-500 group-hover:scale-[1.03]"
          />
        ) : (
          <div className="flex h-full items-center justify-center px-4 text-center text-xs text-[#8C8A82]">
            {item.category_group}
          </div>
        )}
        {item.needs_review && (
          <span className="absolute left-2 top-2 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-800">
            Needs review
          </span>
        )}
        {item.status === "confirmed" && (
          <span className="absolute right-2 top-2 rounded-full bg-[#E8EDE0] px-2 py-0.5 text-[10px] font-semibold text-[#556B2F]">
            Confirmed
          </span>
        )}
      </div>
      <div className="space-y-1.5 p-3">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-[#8C8A82]">
          {item.category_group}
        </p>
        <p className="truncate text-sm font-semibold text-[#1C1C1C]">{item.name}</p>
        <div className="flex items-center gap-1.5 text-[11px] text-[#8C8A82]">
          <span
            className="h-2.5 w-2.5 shrink-0 rounded-full border border-[#E2E0D8]"
            style={{ backgroundColor: item.color_hex ?? "#c8c8c8" }}
          />
          <span className="truncate">
            {cap(item.color_name ?? "unknown")} - {seasonLabel(item.seasons ?? [])}
          </span>
        </div>
        <div className="flex items-center justify-between pt-1">
          <span className="text-[10px] text-[#8C8A82]">{formatDate(item.created_at)}</span>
          <span
            className={`text-[10px] font-semibold ${
              lowConfidence ? "text-amber-700" : "text-[#556B2F]"
            }`}
          >
            {Math.round(confidence * 100)}% sure
          </span>
        </div>
        <div className="h-1 overflow-hidden rounded-full bg-[#E2E0D8]">
          <div
            className={`h-full rounded-full ${lowConfidence ? "bg-amber-500" : "bg-[#556B2F]"}`}
            style={{ width: `${Math.round(confidence * 100)}%` }}
          />
        </div>
      </div>
    </button>
  )
}

export default function WardrobePage() {
  const { items, health, loading, error, reload, addItems, updateItem, reclassifyItem, deleteItem } =
    useWardrobe()

  const [query, setQuery] = useState("")
  const [group, setGroup] = useState("All")
  const [color, setColor] = useState("")
  const [season, setSeason] = useState("")
  const [occasion, setOccasion] = useState("")
  const [style, setStyle] = useState("")
  const [reviewOnly, setReviewOnly] = useState(false)
  const [multi, setMulti] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [view, setView] = useState<"grid" | "3d">("grid")
  const [scanning, setScanning] = useState(false)
  const [jobs, setJobs] = useState<UploadJob[]>([])
  const [addError, setAddError] = useState("")
  const [photoSearching, setPhotoSearching] = useState(false)
  const [photoError, setPhotoError] = useState("")
  const [photoMatch, setPhotoMatch] = useState<WardrobeItem | null | undefined>(undefined)
  // Natural-language search: the agent picks the filters, searches, and explains its answer.
  const [aiBusy, setAiBusy] = useState(false)
  const [ai, setAi] = useState<{ reply: string; ids: string[]; filters: Record<string, string | number>[] } | null>(null)
  // Verdicts of the duplicate agent for photos just added or searched.
  const [dupNotes, setDupNotes] = useState<{ id: string; text: string }[]>([])
  const [held, setHeld] = useState<HeldPhoto[]>([])

  const fileInput = useRef<HTMLInputElement>(null)
  const photoInput = useRef<HTMLInputElement>(null)

  const counts = useMemo(() => {
    const next: Record<string, number> = { All: items.length }
    for (const groupName of TAXONOMY.groups) {
      next[groupName] = items.filter((item) => item.category_group === groupName).length
    }
    return next
  }, [items])

  const colors = useMemo(
    () => [...new Set(items.map((item) => item.color_name).filter(Boolean))].sort() as string[],
    [items],
  )

  const needsReview = items.filter((item) => item.needs_review).length
  const selected = items.find((item) => item.id === selectedId) ?? null

  const shown = useMemo(() => {
    if (photoMatch !== undefined) return photoMatch ? [photoMatch] : []
    if (ai) {
      const byId = new Map(items.map((item) => [item.id, item]))
      return ai.ids.map((id) => byId.get(id)).filter((item): item is WardrobeItem => Boolean(item))
    }
    const words = query.toLowerCase().trim().split(/\s+/).filter(Boolean)
    return items.filter((item) => {
      if (group !== "All" && item.category_group !== group) return false
      if (reviewOnly && !item.needs_review) return false
      if (color && item.color_name !== color) return false
      if (season && !(item.seasons ?? []).includes(season)) return false
      if (occasion && !(item.occasions ?? []).includes(occasion)) return false
      if (style && item.style !== style) return false
      if (words.length) {
        const haystack = itemHaystack(item)
        if (!words.every((word) => haystack.includes(word))) return false
      }
      return true
    })
  }, [items, photoMatch, ai, query, group, reviewOnly, color, season, occasion, style])

  const dismissHeld = (entry: HeldPhoto) => {
    setHeld((previous) => {
      const rest = previous.filter((other) => other.id !== entry.id)
      if (!rest.some((other) => other.preview === entry.preview)) URL.revokeObjectURL(entry.preview)
      return rest
    })
  }

  const addHeldAnyway = async (entry: HeldPhoto) => {
    dismissHeld(entry)
    try {
      const response = await api.analyze(entry.file, { allItems: entry.multi, force: true, only: entry.index })
      addItems(response.items)
    } catch (uploadError) {
      setAddError(uploadError instanceof Error ? uploadError.message : "Could not add this item.")
    }
  }

  const noteDuplicate = (id: string, text: string) =>
    setDupNotes((previous) => [...previous.filter((note) => note.id !== id), { id, text }])

  const clearAi = () => setAi(null)

  const askAi = async (raw?: string) => {
    const text = (raw ?? query).trim()
    if (!text || aiBusy) return
    setAiBusy(true)
    setPhotoMatch(undefined)
    try {
      const response = await api.agentSearch(text)
      setAi({
        reply: response.reply,
        ids: response.items.map((item) => item.id),
        filters: response.filters ?? [],
      })
    } catch (searchError) {
      setAi(null)
      setPhotoError(searchError instanceof Error ? searchError.message : "The AI search failed.")
    } finally {
      setAiBusy(false)
    }
  }

  const speech = useSpeech((text, final) => {
    setQuery(text)
    clearAi()
    if (final && text) void askAi(text)
  })

  const addFiles = async (fileList: FileList | File[] | null) => {
    const files = Array.from(fileList ?? []).filter((file) => file.type.startsWith("image/"))
    if (!files.length) return
    if (health && !health.model_loaded) {
      setAddError("The detection model is not loaded on the server, so new photos cannot be analysed.")
      return
    }
    setAddError("")
    for (const file of files) {
      const jobId = Math.random().toString(36).slice(2)
      const preview = URL.createObjectURL(file)
      setJobs((previous) => [...previous, { id: jobId, preview }])
      try {
        const response = await api.analyze(file, { allItems: multi })
        addItems(response.items)
        setJobs((previous) => previous.filter((job) => job.id !== jobId))
        URL.revokeObjectURL(preview)
        if (response.skipped_items?.length) {
          const heldPreview = URL.createObjectURL(file)
          setHeld((previous) => [
            ...response.skipped_items!.map((entry) => ({
              ...entry,
              id: Math.random().toString(36).slice(2),
              file,
              preview: heldPreview,
              multi,
            })),
            ...previous,
          ])
        }
        // The duplicate agent searches the wardrobe (without the new item) for a near-duplicate.
        for (const added of response.items) {
          api
            .checkDuplicate(added)
            .then((verdict) => {
              if (verdict.duplicate) {
                noteDuplicate(added.id, `${added.name}: ${verdict.note || "looks like one you already have"}`)
              }
            })
            .catch(() => {})
        }
      } catch (uploadError) {
        const message =
          uploadError instanceof Error ? uploadError.message : "Could not analyse this photo."
        setJobs((previous) =>
          previous.map((job) => (job.id === jobId ? { ...job, error: message } : job)),
        )
        window.setTimeout(() => {
          setJobs((previous) => previous.filter((job) => job.id !== jobId))
          URL.revokeObjectURL(preview)
        }, 7000)
      }
    }
  }

  const searchByPhoto = async (file: File | undefined) => {
    if (!file) return
    setPhotoSearching(true)
    setPhotoError("")
    setPhotoMatch(undefined)
    clearAi()
    try {
      const response = await api.searchByPhoto(file)
      setPhotoMatch(response.match)
      // Nothing was saved, so the agent can compare the photographed garment to the whole wardrobe.
      api
        .checkDuplicate({ category: response.category, color_name: response.color_name })
        .then((verdict) => {
          if (verdict.duplicate) noteDuplicate("photo-search", verdict.note || "You already own something very similar.")
        })
        .catch(() => {})
    } catch (searchError) {
      setPhotoError(
        searchError instanceof Error ? searchError.message : "Could not search by photo.",
      )
    } finally {
      setPhotoSearching(false)
    }
  }

  const clearPhotoSearch = () => {
    setPhotoMatch(undefined)
    setPhotoError("")
    setDupNotes((previous) => previous.filter((note) => note.id !== "photo-search"))
  }

  if (loading && !items.length) {
    return (
      <div className="flex min-h-[320px] items-center justify-center text-sm text-[#8C8A82]">
        Loading your wardrobe...
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">My Wardrobe</h1>
          <p className="mt-1 text-sm text-[#8C8A82]">
            {items.length} {items.length === 1 ? "item" : "items"} - {needsReview} to review
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <div className="flex rounded-lg border border-[#E2E0D8] bg-white p-0.5">
            {(["grid", "3d"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setView(mode)}
                className={`rounded-md px-3 py-2 text-sm font-semibold transition-colors ${
                  view === mode
                    ? "bg-[#1C1C1C] text-white"
                    : "text-[#1C1C1C] hover:bg-[#F0EFEA]"
                }`}
              >
                {mode === "grid" ? "Grid" : "3D"}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => void reload()}
            className="rounded-lg border border-[#E2E0D8] bg-white px-4 py-2.5 text-sm font-semibold text-[#1C1C1C] transition-colors hover:bg-[#F0EFEA]"
          >
            Refresh
          </button>
          <button
            type="button"
            onClick={() => setScanning(true)}
            disabled={Boolean(health && !health.model_loaded)}
            className="rounded-lg border border-[#E2E0D8] bg-white px-4 py-2.5 text-sm font-semibold text-[#1C1C1C] transition-colors hover:bg-[#F0EFEA] disabled:cursor-not-allowed disabled:opacity-40"
          >
            Live scan
          </button>
          <button
            type="button"
            onClick={() => fileInput.current?.click()}
            disabled={Boolean(health && !health.model_loaded)}
            className="rounded-lg bg-[#1C1C1C] px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#333] disabled:cursor-not-allowed disabled:opacity-40"
          >
            Add clothing
          </button>
          <input
            ref={fileInput}
            type="file"
            accept="image/*"
            multiple
            hidden
            onChange={(event) => {
              void addFiles(event.target.files)
              event.target.value = ""
            }}
          />
        </div>
      </div>

      {(error || photoError || addError) && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <span>{error ?? photoError ?? addError}</span>
          <button
            type="button"
            onClick={() => {
              setAddError("")
              setPhotoError("")
              void reload()
            }}
            className="rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-semibold text-red-700"
          >
            Try again
          </button>
        </div>
      )}

      {held.length > 0 && (
        <div className="space-y-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <p className="font-semibold">Not added yet - your call</p>
          {held.map((entry) => (
            <div key={entry.id} className="flex flex-wrap items-center gap-3 rounded-lg bg-white/70 p-2">
              <img src={entry.preview} alt="" className="h-16 w-14 shrink-0 rounded bg-[#F0EFEA] object-cover" />
              {entry.similar_item?.cutout_url && (
                <>
                  <span className="text-xs text-[#8C8A82]">vs</span>
                  <img
                    src={asset(entry.similar_item.cutout_url)}
                    alt={entry.similar_item.name}
                    className="h-16 w-14 shrink-0 rounded bg-[#F0EFEA] object-contain"
                  />
                </>
              )}
              <div className="min-w-0 flex-1">
                <p className="font-medium">{cap(entry.category)} not added</p>
                <p>{entry.note}</p>
              </div>
              <div className="flex gap-3 text-xs">
                <button
                  type="button"
                  onClick={() => void addHeldAnyway(entry)}
                  className="rounded-lg bg-[#556B2F] px-3 py-1.5 font-semibold text-white hover:bg-[#6B8A3A]"
                >
                  Add anyway
                </button>
                <button type="button" onClick={() => dismissHeld(entry)} className="underline">
                  Dismiss
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {speech.error && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {speech.error}
        </div>
      )}

      {dupNotes.length > 0 && (
        <div className="space-y-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <p className="font-semibold">Possible duplicate</p>
          {dupNotes.map((note) => (
            <div key={note.id} className="flex items-start justify-between gap-3">
              <span>{note.text}</span>
              <button
                type="button"
                onClick={() => setDupNotes((previous) => previous.filter((entry) => entry.id !== note.id))}
                className="shrink-0 text-xs underline"
              >
                Dismiss
              </button>
            </div>
          ))}
        </div>
      )}

      {health && !health.model_loaded && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          The detection model is not loaded on the server. You can still browse and edit existing
          items, but new photos cannot be analysed right now.
        </div>
      )}

      {view === "3d" && (
        <Suspense
          fallback={
            <div className="flex min-h-[320px] items-center justify-center rounded-xl bg-[#F0EFEA] text-sm text-[#8C8A82]">
              Loading 3D wardrobe...
            </div>
          }
        >
          <Wardrobe3D items={items} selectedId={selectedId} onSelect={setSelectedId} />
        </Suspense>
      )}

      {view === "grid" && (
        <>
      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div
          onClick={() => fileInput.current?.click()}
          onDragOver={(event) => {
            event.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault()
            setDragging(false)
            void addFiles(event.dataTransfer.files)
          }}
          className={`cursor-pointer rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors ${
            dragging
              ? "border-[#556B2F] bg-[#E8EDE0]"
              : "border-[#E2E0D8] bg-[#F0EFEA] hover:border-[#556B2F]"
          }`}
        >
          <p className="text-sm font-medium text-[#1C1C1C]">
            Drop photos here, or click to add clothing
          </p>
          <p className="mt-1 text-xs text-[#8C8A82]">
            Each item is detected, cut out, and classified by occasion, style, colour and season.
          </p>
          <label
            className="mt-3 inline-flex items-center gap-2 text-xs font-medium text-[#1C1C1C]"
            onClick={(event) => event.stopPropagation()}
          >
            <input
              type="checkbox"
              checked={multi}
              onChange={(event) => setMulti(event.target.checked)}
              className="accent-[#556B2F]"
            />
            Photo of a full outfit - add every item found
          </label>
        </div>

        <div className="rounded-xl border border-[#E2E0D8] bg-white p-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
            Find by photo
          </p>
          <p className="mt-1 text-xs text-[#8C8A82]">
            Upload a photo of a garment to find the closest item you already own.
          </p>
          <button
            type="button"
            disabled={photoSearching || Boolean(health && !health.model_loaded)}
            onClick={() => photoInput.current?.click()}
            className="mt-3 w-full rounded-lg border border-[#E2E0D8] px-3 py-2 text-xs font-semibold text-[#1C1C1C] transition-colors hover:bg-[#F0EFEA] disabled:opacity-40"
          >
            {photoSearching ? "Searching..." : "Choose a photo"}
          </button>
          <input
            ref={photoInput}
            type="file"
            accept="image/*"
            hidden
            onChange={(event) => {
              void searchByPhoto(event.target.files?.[0])
              event.target.value = ""
            }}
          />
          {photoMatch !== undefined && !photoSearching && (
            <div className="mt-3 rounded-lg bg-[#F0EFEA] px-3 py-2 text-xs text-[#1C1C1C]">
              {photoMatch ? (
                <button
                  type="button"
                  onClick={() => setSelectedId(photoMatch.id)}
                  className="font-semibold text-[#556B2F] hover:underline"
                >
                  That looks like your {photoMatch.name}
                </button>
              ) : (
                <span>No similar item found in your wardrobe yet.</span>
              )}
              <button
                type="button"
                onClick={clearPhotoSearch}
                className="ml-2 text-[#8C8A82] underline"
              >
                Clear
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="space-y-3">
        <div className="flex flex-wrap gap-2">
          <div className="flex min-w-[240px] flex-1 items-center gap-2 rounded-lg border border-[#E2E0D8] bg-white px-3 py-2">
            <svg
              viewBox="0 0 24 24"
              width="18"
              height="18"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              className="text-[#8C8A82]"
            >
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-4-4" />
            </svg>
            <input
              value={query}
              onChange={(event) => {
                setQuery(event.target.value)
                clearPhotoSearch()
                clearAi()
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") void askAi()
              }}
              placeholder='Search, or ask: "a warm jacket for a cold day"'
              className="w-full bg-transparent text-sm text-[#1C1C1C] outline-none placeholder:text-[#8C8A82]"
            />
            {speech.supported && (
              <button
                type="button"
                title={speech.listening ? "Stop listening" : "Search by voice"}
                aria-label="Search by voice"
                onClick={speech.toggle}
                className={`rounded-full p-1.5 transition-colors ${
                  speech.listening ? "animate-pulse bg-red-100 text-red-600" : "text-[#8C8A82] hover:bg-[#F0EFEA]"
                }`}
              >
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <rect x="9" y="3" width="6" height="11" rx="3" />
                  <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
                </svg>
              </button>
            )}
            <button
              type="button"
              disabled={aiBusy || !query.trim()}
              onClick={() => void askAi()}
              className="shrink-0 rounded-md bg-[#556B2F] px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-[#6B8A3A] disabled:opacity-40"
            >
              {aiBusy ? "Searching..." : "Ask AI"}
            </button>
          </div>
          {[
            { value: color, set: setColor, label: "All colours", options: colors },
            { value: season, set: setSeason, label: "All seasons", options: TAXONOMY.seasons },
            { value: occasion, set: setOccasion, label: "All occasions", options: TAXONOMY.occasions },
            { value: style, set: setStyle, label: "All styles", options: TAXONOMY.styles },
          ].map((filter) => (
            <select
              key={filter.label}
              value={filter.value}
              onChange={(event) => filter.set(event.target.value)}
              className="rounded-lg border border-[#E2E0D8] bg-white px-3 py-2 text-sm capitalize text-[#1C1C1C] outline-none focus:border-[#556B2F]"
            >
              <option value="">{filter.label}</option>
              {filter.options.map((option) => (
                <option key={option} value={option}>
                  {cap(option)}
                </option>
              ))}
            </select>
          ))}
        </div>

        <div className="flex flex-wrap gap-2">
          {["All", ...TAXONOMY.groups]
            .filter((groupName) => groupName === "All" || counts[groupName] > 0)
            .map((groupName) => (
              <button
                key={groupName}
                type="button"
                onClick={() => setGroup(groupName)}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                  group === groupName
                    ? "border-[#1C1C1C] bg-[#1C1C1C] text-white"
                    : "border-[#E2E0D8] bg-white text-[#1C1C1C] hover:border-[#556B2F]"
                }`}
              >
                {groupName} <span className="opacity-60">{counts[groupName] ?? 0}</span>
              </button>
            ))}
          {needsReview > 0 && (
            <button
              type="button"
              onClick={() => setReviewOnly((previous) => !previous)}
              className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                reviewOnly
                  ? "border-amber-600 bg-amber-600 text-white"
                  : "border-amber-200 bg-amber-50 text-amber-800 hover:border-amber-500"
              }`}
            >
              Needs review ({needsReview})
            </button>
          )}
        </div>
      </div>

      {ai && (
        <div className="space-y-2 rounded-xl border border-[#556B2F]/30 bg-[#E8EDE0] px-4 py-3 text-sm text-[#1C1C1C]">
          <p className="text-xs font-semibold uppercase tracking-widest text-[#556B2F]">AI search</p>
          {ai.filters.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {ai.filters.flatMap((entry, index) =>
                Object.entries(entry).map(([key, value]) => (
                  <span
                    key={`${index}-${key}`}
                    className="rounded-full bg-white px-2.5 py-0.5 text-xs text-[#556B2F]"
                  >
                    {key.replace(/_/g, " ")}: {String(value)}
                  </span>
                )),
              )}
            </div>
          )}
          <p className="whitespace-pre-line leading-relaxed">{ai.reply}</p>
          <button type="button" onClick={clearAi} className="text-xs text-[#556B2F] underline">
            Clear AI search
          </button>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {jobs.map((job) => (
          <div
            key={job.id}
            className={`overflow-hidden rounded-xl border bg-white ${
              job.error ? "border-red-200" : "border-[#E2E0D8]"
            }`}
          >
            <div className="relative aspect-[4/5] overflow-hidden bg-[#F0EFEA]">
              <img src={job.preview} alt="" className="h-full w-full object-cover opacity-40" />
              {!job.error && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="rounded-full bg-[#1C1C1C] px-3 py-1.5 text-xs font-semibold text-white">
                    Analysing...
                  </span>
                </div>
              )}
            </div>
            <div className="p-3 text-xs">
              {job.error ? (
                <p className="text-red-700">{job.error}</p>
              ) : (
                <p className="text-[#8C8A82]">Detecting, cutting out, and classifying.</p>
              )}
            </div>
          </div>
        ))}

        {shown.map((item) => (
          <ItemCard key={item.id} item={item} onSelect={setSelectedId} />
        ))}
      </div>

      {!shown.length && !jobs.length && (
        <div className="rounded-xl border border-[#E2E0D8] bg-[#F0EFEA] px-6 py-10 text-center text-sm text-[#8C8A82]">
          {items.length
            ? "No items match these filters."
            : "Your wardrobe is empty. Add a photo of a clothing item to start."}
        </div>
      )}
        </>
      )}

      {scanning && (
        <LiveScan onAdded={addItems} onClose={() => setScanning(false)} />
      )}

      {selected && (
        <ItemDrawer
          key={selected.id}
          item={selected}
          health={health}
          onClose={() => setSelectedId(null)}
          onSave={updateItem}
          onReclassify={reclassifyItem}
          onDelete={async (id) => {
            await deleteItem(id)
            setSelectedId(null)
          }}
        />
      )}
    </div>
  )
}
