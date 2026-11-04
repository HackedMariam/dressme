import { useEffect, useMemo, useRef, useState } from "react"
import { api, asset } from "../../lib/api"
import { tryOnGroup } from "../../lib/pieces"
import { TAXONOMY, cap, seasonLabel } from "../../lib/taxonomy"
import type { WardrobeItem } from "../../lib/types"
import TryOnModal, { type Garment } from "../shop/TryOnModal"
import { useWardrobe } from "../wardrobe/WardrobeProvider"
import { fetchPlanPhotos, type WebPhoto } from "../wardrobegaps/api"

type Status = "owned" | "close" | "missing"
type Part = { piece: WardrobeItem; status: Status; match: { item: WardrobeItem; score: number; reasons: string[] } | null }
type Pending = { garment: Garment; group: string; label: string }

const STATUS: Record<Status, { label: string; badge: string }> = {
  owned: { label: "You own it", badge: "bg-[#556B2F] text-white" },
  close: { label: "Close match", badge: "bg-amber-600 text-white" },
  missing: { label: "Missing", badge: "bg-[#1C1C1C] text-white" },
}

// What to look for in Tunisian shops for each garment the detector can name (BO3 searches a fixed French catalogue).
const SHOP_SEARCH: Record<string, string> = {
  top: "t-shirt", sweater: "sweater", jacket: "light_jacket", vest: "cardigan", pants: "trousers", shorts: "shorts",
  skirt: "skirt", dress: "cocktail_dress", shoe: "sneakers", bag: "tote", hat: "hat", scarf: "scarf", belt: "belt",
  glasses: "sunglasses", glove: "gloves", sock: "socks", tights: "tights", umbrella: "umbrella", headband: "headband",
}

function similarity(owned: WardrobeItem, piece: WardrobeItem) {
  const reasons: string[] = []
  let score = 0
  if (owned.category === piece.category) {
    score += 55
    reasons.push("Same type")
  } else if (owned.category_group === piece.category_group) {
    score += 15
    reasons.push("Same group")
  }
  if (piece.color_name && owned.color_name === piece.color_name) {
    score += 30
    reasons.push("Same colour")
  } else if (piece.color_family && owned.color_family === piece.color_family) {
    score += 15
    reasons.push("Similar colour")
  }
  return { score, reasons }
}

function statusOf(score: number): Status {
  return score >= 85 ? "owned" : score >= 55 ? "close" : "missing"
}

function OwnedMatch({ item, score, reasons }: { item: WardrobeItem; score: number; reasons: string[] }) {
  return (
    <div className="flex gap-3 rounded-lg bg-[#FAF9F6] p-2.5">
      <div className="flex h-20 w-16 shrink-0 items-center justify-center overflow-hidden rounded-md bg-[#F0EFEA]">
        {item.cutout_url ? (
          <img src={asset(item.cutout_url)} alt={item.name} loading="lazy" className="h-full w-full object-contain" />
        ) : null}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-[#1C1C1C]">{item.name}</p>
        <p className="truncate text-[11px] text-[#8C8A82]">
          {cap(item.color_name ?? "unknown")} - {seasonLabel(item.seasons ?? [])}
        </p>
        <div className="mt-1.5 flex items-center gap-2">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[#E2E0D8]">
            <div className="h-full rounded-full bg-[#556B2F]" style={{ width: `${score}%` }} />
          </div>
          <span className="text-[11px] font-semibold text-[#1C1C1C]">{score}%</span>
        </div>
        <div className="mt-1 flex flex-wrap gap-1">
          {reasons.map((reason) => (
            <span key={reason} className="rounded-full bg-white px-2 py-0.5 text-[10px] font-medium text-[#556B2F]">
              {reason}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}

function ShopRow({ piece, index, onTryOn }: { piece: WardrobeItem; index: number; onTryOn: (pending: Pending) => void }) {
  const [photos, setPhotos] = useState<WebPhoto[] | null>(null)
  const [failed, setFailed] = useState(false)
  const search = SHOP_SEARCH[piece.category]
  const group = tryOnGroup(piece.category)

  useEffect(() => {
    if (!search) {
      setPhotos([])
      return
    }
    let cancelled = false
    // One web search per second at most: the free search engine throttles bursts.
    const timer = setTimeout(() => {
      fetchPlanPhotos(piece.category, search, 3)
        .then((reply) => !cancelled && setPhotos(reply.images))
        .catch(() => {
          if (cancelled) return
          setFailed(true)
          setPhotos([])
        })
    }, index * 900)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [piece.category, search, index])

  if (photos && photos.length === 0) {
    return (
      <p className="rounded-lg bg-[#FAF9F6] px-3 py-2 text-xs text-[#8C8A82]">
        {failed
          ? "Shop search is unavailable right now (the shop service on port 8001 is not running)."
          : "No Tunisian shop photo found for this piece."}
      </p>
    )
  }

  return (
    <div className="grid grid-cols-3 gap-2">
      {photos === null
        ? [0, 1, 2].map((slot) => <div key={slot} className="aspect-[3/4] animate-pulse rounded-lg bg-[#F0EFEA]" />)
        : photos.map((photo) => (
            <div key={photo.page_url} className="space-y-1">
              <a
                href={photo.page_url}
                target="_blank"
                rel="noopener noreferrer"
                title={photo.title}
                className="group relative block aspect-[3/4] overflow-hidden rounded-lg bg-[#F0EFEA]"
              >
                <img
                  src={photo.thumbnail}
                  alt={photo.title}
                  loading="lazy"
                  referrerPolicy="no-referrer"
                  onError={(event) => (event.currentTarget.style.visibility = "hidden")}
                  className="h-full w-full object-cover transition-transform group-hover:scale-[1.03]"
                />
                <span className="absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/60 to-transparent px-1.5 pb-1 pt-5 text-[10px] font-semibold text-white">
                  {photo.source} {"↗"}
                </span>
              </a>
              {group && (
                <button
                  type="button"
                  onClick={() =>
                    onTryOn({ garment: { imageUrl: photo.thumbnail }, group, label: `${cap(piece.category)} - ${photo.source}` })
                  }
                  className="w-full rounded-md bg-[#1C1C1C] px-1 py-1 text-[10px] font-semibold text-white hover:bg-black"
                >
                  Virtual try-on
                </button>
              )}
            </div>
          ))}
    </div>
  )
}

// "Recreate this look": the user shows a photo of an outfit they like; every garment in it is compared with
// the wardrobe, and what is missing is searched in Tunisian shops, with a virtual try-on.
export default function FindSimilarPage({ onOpenAvatar }: { onOpenAvatar?: () => void }) {
  const { items } = useWardrobe()
  const [pieces, setPieces] = useState<WardrobeItem[] | null>(null)
  const [preview, setPreview] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [pending, setPending] = useState<Pending | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    return () => {
      if (preview.startsWith("blob:")) URL.revokeObjectURL(preview)
    }
  }, [preview])

  const analyse = async (file: File | undefined) => {
    if (!file) return
    setError("")
    setPieces(null)
    setPreview(URL.createObjectURL(file))
    setBusy(true)
    try {
      const response = await api.analyze(file, { allItems: true, save: false, fast: true })
      setPieces(response.items)
    } catch (analyseError) {
      setError(analyseError instanceof Error ? analyseError.message : "Could not analyse this photo.")
    } finally {
      setBusy(false)
    }
  }

  const parts = useMemo<Part[]>(() => {
    if (!pieces) return []
    return pieces.map((piece) => {
      const ranked = items
        .map((item) => ({ item, ...similarity(item, piece) }))
        .filter((entry) => entry.score >= 45)
        .sort((a, b) => b.score - a.score)
      const match = ranked[0] ?? null
      return { piece, status: statusOf(match?.score ?? 0), match }
    })
  }, [pieces, items])

  const counts = {
    owned: parts.filter((part) => part.status === "owned").length,
    close: parts.filter((part) => part.status === "close").length,
    missing: parts.filter((part) => part.status === "missing").length,
  }
  const coverage = parts.length ? Math.round(((counts.owned + counts.close * 0.5) / parts.length) * 100) : 0
  const missingParts = parts.filter((part) => part.status === "missing")

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Find Similar</h1>
        <p className="mt-1 text-sm text-[#8C8A82]">
          Show a look you like. See how much of it you can already recreate, and where to find the rest.
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <div className="space-y-4">
          <div className="rounded-xl border border-[#E2E0D8] bg-[#F0EFEA] p-5">
            <p className="text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">Inspiration photo</p>
            {preview ? (
              <img src={preview} alt="Look to recreate" className="mt-3 max-h-80 w-full rounded-lg bg-white object-contain p-2" />
            ) : (
              <p className="mt-1 text-xs text-[#8C8A82]">
                A full outfit from Pinterest, Instagram, a magazine or a shop window. Each garment is detected separately.
              </p>
            )}
            <button
              type="button"
              disabled={busy}
              onClick={() => fileInput.current?.click()}
              className="mt-3 w-full rounded-lg bg-[#1C1C1C] px-3 py-2.5 text-xs font-semibold text-white transition-colors hover:bg-[#333] disabled:opacity-40"
            >
              {busy ? "Detecting garments..." : preview ? "Use another look" : "Choose a photo"}
            </button>
            <input
              ref={fileInput}
              type="file"
              accept="image/*"
              hidden
              onChange={(event) => {
                void analyse(event.target.files?.[0])
                event.target.value = ""
              }}
            />
          </div>
          <p className="text-xs text-[#8C8A82]">
            Want a buy-or-skip verdict for a single piece with your budget? Use Should I Buy.
          </p>
        </div>

        <div className="space-y-4">
          {busy && (
            <div className="flex min-h-[240px] items-center justify-center rounded-xl bg-[#F0EFEA] text-sm text-[#8C8A82]">
              Finding every garment in the photo...
            </div>
          )}

          {!busy && pieces && parts.length > 0 && (
            <>
              <div className="rounded-xl border border-[#E2E0D8] bg-white p-5">
                <div className="flex flex-wrap items-end justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">You can recreate</p>
                    <p className="font-display text-3xl font-semibold text-[#1C1C1C]">
                      {coverage}% <span className="text-base font-normal text-[#8C8A82]">of this look</span>
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2 text-[11px] font-semibold">
                    <span className="rounded-full bg-[#E8EDE0] px-2.5 py-1 text-[#556B2F]">{counts.owned} owned</span>
                    <span className="rounded-full bg-amber-50 px-2.5 py-1 text-amber-700">{counts.close} close</span>
                    <span className="rounded-full bg-[#F0EFEA] px-2.5 py-1 text-[#1C1C1C]">{counts.missing} to find</span>
                  </div>
                </div>
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-[#E2E0D8]">
                  <div className="h-full rounded-full bg-[#556B2F] transition-all" style={{ width: `${coverage}%` }} />
                </div>
              </div>

              {parts.map((part) => {
                const { piece, status, match } = part
                const shopIndex = missingParts.indexOf(part)
                return (
                  <div key={piece.id} className="rounded-xl border border-[#E2E0D8] bg-white p-4">
                    <div className="flex items-center gap-3">
                      <div className="flex h-16 w-14 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-[#F0EFEA]">
                        {piece.cutout_url ? (
                          <img src={asset(piece.cutout_url)} alt={piece.category} className="h-full w-full object-contain" />
                        ) : null}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold text-[#1C1C1C]">
                          {cap(piece.color_name ?? "")} {piece.category}
                        </p>
                        <p className="text-[11px] text-[#8C8A82]">
                          {TAXONOMY.class_to_group[piece.category] ?? piece.category_group} in the photo
                        </p>
                      </div>
                      <span className={`rounded-md px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider ${STATUS[status].badge}`}>
                        {STATUS[status].label}
                      </span>
                    </div>

                    {match && status !== "missing" && (
                      <div className="mt-3">
                        <OwnedMatch item={match.item} score={match.score} reasons={match.reasons} />
                      </div>
                    )}

                    {status === "missing" && (
                      <div className="mt-3 space-y-2">
                        <p className="text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
                          Find it in Tunisian shops
                        </p>
                        <ShopRow piece={piece} index={shopIndex} onTryOn={setPending} />
                      </div>
                    )}
                  </div>
                )
              })}
            </>
          )}

          {!busy && !pieces && (
            <div className="flex min-h-[320px] flex-col items-center justify-center rounded-xl border border-[#E2E0D8] bg-[#F0EFEA] px-8 text-center">
              <p className="font-medium text-[#1C1C1C]">Recreate a look with what you own</p>
              <p className="mt-1 max-w-sm text-sm text-[#8C8A82]">
                Each garment in your photo is matched with your wardrobe. What you do not have is searched in Tunisian
                shops, and you can try it on your avatar before buying.
              </p>
            </div>
          )}
        </div>
      </div>

      {pending && (
        <TryOnModal
          garment={pending.garment}
          group={pending.group}
          label={pending.label}
          onClose={() => setPending(null)}
          onOpenAvatar={onOpenAvatar}
        />
      )}
    </div>
  )
}
