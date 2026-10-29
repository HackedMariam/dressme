import { lazy, Suspense, useMemo, useRef, useState } from "react"
import { api, asset } from "../../lib/api"
import { COLORS, TAXONOMY, cap, formatDate, seasonLabel } from "../../lib/taxonomy"
import type { WardrobeItem } from "../../lib/types"
import ItemDrawer from "./ItemDrawer"
import LiveScan from "./LiveScan"
import { useWardrobe } from "./WardrobeProvider"
import { useAuth } from "../auth/AuthProvider"
import { saveGalleryPhoto } from "../../lib/photoGallery"

const Wardrobe3D = lazy(() => import("./Wardrobe3D"))

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
  const { user } = useAuth()
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
  }, [items, photoMatch, query, group, reviewOnly, color, season, occasion, style])

  const addFiles = async (fileList: FileList | File[] | null) => {
    const files = Array.from(fileList ?? []).filter((file) => file.type.startsWith("image/"))
    if (!files.length) return
    if (health && !health.model_loaded) {
      setAddError("The detection model is not loaded on the server, so new photos cannot be analysed.")
      return
    }
    setAddError("")
    for (const file of files) {
      if (user?.id) {
        void saveGalleryPhoto(user.id, file, "wardrobe").catch((error) => {
          setAddError(error instanceof Error ? error.message : "Could not save this photo to your gallery.")
        })
      }
      const jobId = Math.random().toString(36).slice(2)
      const preview = URL.createObjectURL(file)
      setJobs((previous) => [...previous, { id: jobId, preview }])
      try {
        const response = await api.analyze(file, { allItems: multi })
        addItems(response.items)
        setJobs((previous) => previous.filter((job) => job.id !== jobId))
        URL.revokeObjectURL(preview)
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
    try {
      const response = await api.searchByPhoto(file)
      setPhotoMatch(response.match)
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
              }}
              placeholder="Search by name, colour, occasion, material..."
              className="w-full bg-transparent text-sm text-[#1C1C1C] outline-none placeholder:text-[#8C8A82]"
            />
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
        <LiveScan userId={user?.id} onAdded={addItems} onClose={() => setScanning(false)} />
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
          onMeshUpdated={() => void reload()}
          onItemUpdated={() => void reload()}
        />
      )}
    </div>
  )
}
