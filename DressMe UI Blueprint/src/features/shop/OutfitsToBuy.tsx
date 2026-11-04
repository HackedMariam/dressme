import { useEffect, useRef, useState } from "react"
import { inferCategory, tryOnGroup } from "../../lib/pieces"
import {
  fetchGapImages,
  fetchGaps,
  fetchGoals,
  type Goal,
  type GapRanking,
  type RankedGap,
  type WebPhoto,
} from "../wardrobegaps/api"
import TryOnModal, { type Garment } from "./TryOnModal"

type Pending = { garment: Garment; group: string; label: string }

export const SHOP_GOAL_KEY = "dressme.shopGoal"
const TRYON_GROUP_CHOICES = ["Tops", "Outerwear", "Bottoms", "Dresses"]

// Each web search takes about a second and the free search engine throttles bursts: pieces load one after another.
const STAGGER_MS = 900

function storedGoal() {
  try {
    return localStorage.getItem(SHOP_GOAL_KEY) ?? ""
  } catch {
    return ""
  }
}

function ProductCard({
  photo,
  piece,
  group,
  onTryOn,
}: {
  photo: WebPhoto
  piece: string
  group: string | null
  onTryOn: (pending: Pending) => void
}) {
  return (
    <div className="w-52 shrink-0 snap-start overflow-hidden rounded-xl border border-[#E2E0D8] bg-white">
      <a
        href={photo.page_url}
        target="_blank"
        rel="noopener noreferrer"
        className="relative block aspect-[3/4] bg-[#F0EFEA]"
        title={photo.title}
      >
        <img
          src={photo.thumbnail}
          alt={photo.title}
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={(event) => (event.currentTarget.style.visibility = "hidden")}
          className="h-full w-full object-cover"
        />
      </a>
      <div className="space-y-2 p-3">
        <div>
          <p className="line-clamp-2 min-h-[2.5rem] text-sm font-semibold leading-snug text-[#1C1C1C]">
            {photo.title || piece}
          </p>
          <p className="mt-0.5 truncate text-[11px] text-[#8C8A82]">{photo.source}</p>
        </div>
        <div className="flex gap-2">
          <a
            href={photo.page_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-1 rounded-lg bg-[#F0EFEA] px-2 py-2 text-center text-xs font-semibold text-[#1C1C1C] hover:bg-[#E2E0D8]"
          >
            View in shop
          </a>
          {group && (
            <button
              type="button"
              onClick={() => onTryOn({ garment: { imageUrl: photo.thumbnail }, group, label: `${piece} - ${photo.source}` })}
              className="flex-1 rounded-lg bg-[#1C1C1C] px-2 py-2 text-xs font-semibold text-white hover:bg-black"
            >
              Try on
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

function PieceRow({
  gap,
  goal,
  index,
  onTryOn,
}: {
  gap: RankedGap
  goal: string
  index: number
  onTryOn: (pending: Pending) => void
}) {
  const [state, setState] = useState<{ photos: WebPhoto[]; message: string | null } | null>(null)
  const piece = gap.suggested_item || gap.name
  const group = tryOnGroup(inferCategory(`${piece} ${gap.name}`))

  useEffect(() => {
    let cancelled = false
    setState(null)
    const timer = setTimeout(() => {
      fetchGapImages(goal, gap.candidate_id, 6)
        .then((reply) => !cancelled && setState({ photos: reply.images, message: reply.message }))
        .catch((error: Error) => !cancelled && setState({ photos: [], message: error.message }))
    }, index * STAGGER_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [goal, gap.candidate_id, index])

  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex items-center gap-2">
          <h3 className="text-base font-semibold capitalize text-[#1C1C1C]">{piece}</h3>
          <span
            className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
              gap.priority === "high" ? "bg-amber-50 text-amber-700" : "bg-[#E8EDE0] text-[#556B2F]"
            }`}
          >
            {gap.priority}
          </span>
        </div>
        <p className="text-xs text-[#8C8A82]">
          Missing from your wardrobe
          {gap.pairable_owned_items > 0
            ? ` - goes with ${gap.pairable_owned_items} piece${gap.pairable_owned_items === 1 ? "" : "s"} you own`
            : ""}
        </p>
      </div>

      <div className="mt-3 flex snap-x gap-3 overflow-x-auto pb-2">
        {state === null &&
          [0, 1, 2, 3].map((slot) => (
            <div key={slot} className="h-[22rem] w-52 shrink-0 animate-pulse rounded-xl bg-[#E8E6DF]" />
          ))}
        {state?.photos.map((photo) => (
          <ProductCard key={photo.page_url} photo={photo} piece={piece} group={group} onTryOn={onTryOn} />
        ))}
      </div>
      {state && state.photos.length === 0 && (
        <p className="rounded-lg bg-white/70 px-3 py-2 text-xs text-[#8C8A82]">
          {state.message ?? "No Tunisian shop product found for this piece right now."}
        </p>
      )}
      {!group && (
        <p className="mt-1 text-[11px] text-[#8C8A82]">Try-on covers tops, jackets, bottoms and dresses.</p>
      )}
    </div>
  )
}

// Dashboard section: pieces your wardrobe is missing, shown as products of real Tunisian shops, with a virtual try-on.
export default function OutfitsToBuy({ onOpenAvatar }: { onOpenAvatar?: () => void }) {
  const [goals, setGoals] = useState<Goal[]>([])
  const [goal, setGoal] = useState(storedGoal)
  const [ranking, setRanking] = useState<GapRanking | null>(null)
  const [error, setError] = useState("")
  const [pending, setPending] = useState<Pending | null>(null)
  const [shopGroup, setShopGroup] = useState("Tops")
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    fetchGoals()
      .then((list) => {
        setGoals(list)
        setGoal((current) => current || list[0]?.id || "winter_work")
      })
      .catch(() => setGoal((current) => current || "winter_work"))
  }, [])

  useEffect(() => {
    if (!goal) return
    try {
      localStorage.setItem(SHOP_GOAL_KEY, goal)
    } catch {
      // a remembered occasion is only a convenience
    }
    let cancelled = false
    setRanking(null)
    setError("")
    fetchGaps(goal)
      .then((reply) => !cancelled && setRanking(reply))
      .catch((gapError: Error) => !cancelled && setError(gapError.message))
    return () => {
      cancelled = true
    }
  }, [goal])

  const gaps = ranking?.ranked_gaps.slice(0, 3) ?? []

  return (
    <section className="rounded-xl bg-[#F0EFEA] p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-medium text-[#1C1C1C]">Outfits to buy</h2>
          <p className="mt-1 text-xs text-[#8C8A82]">
            Pieces your wardrobe is missing, found in Tunisian shops. Try them on your avatar first.
          </p>
        </div>
        {goals.length > 0 && (
          <select
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            className="rounded-lg border border-[#E2E0D8] bg-white px-3 py-1.5 text-xs text-[#1C1C1C]"
            aria-label="Occasion"
          >
            {goals.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.label}
              </option>
            ))}
          </select>
        )}
      </div>

      {error && (
        <p className="mt-4 rounded-lg bg-white/70 px-3 py-2 text-xs text-[#8C8A82]">
          Suggestions unavailable: {error}. Check that the shop service is running on port 8001.
        </p>
      )}
      {!ranking && !error && <p className="mt-4 text-xs text-[#8C8A82]">Looking at what your wardrobe is missing...</p>}
      {ranking && gaps.length === 0 && (
        <p className="mt-4 text-sm text-[#8C8A82]">Nothing important is missing for this occasion.</p>
      )}

      {gaps.length > 0 && (
        <div className="mt-5 space-y-7">
          {gaps.map((gap, index) => (
            <PieceRow key={`${goal}-${gap.candidate_id}`} gap={gap} goal={goal} index={index} onTryOn={setPending} />
          ))}
        </div>
      )}

      <div className="mt-6 flex flex-wrap items-center gap-3 rounded-xl border border-dashed border-[#C9C6BA] bg-white/60 p-4">
        <div className="min-w-[200px] flex-1">
          <p className="text-sm font-semibold text-[#1C1C1C]">In a shop right now?</p>
          <p className="text-xs text-[#8C8A82]">Take a photo of a piece and see it on you before you buy.</p>
        </div>
        <select
          value={shopGroup}
          onChange={(event) => setShopGroup(event.target.value)}
          className="rounded-lg border border-[#E2E0D8] bg-white px-3 py-2 text-xs"
          aria-label="Type of piece"
        >
          {TRYON_GROUP_CHOICES.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => fileInput.current?.click()}
          className="rounded-lg bg-[#1C1C1C] px-4 py-2 text-xs font-semibold text-white hover:bg-black"
        >
          Photo of a piece
        </button>
        <input
          ref={fileInput}
          type="file"
          accept="image/*"
          capture="environment"
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0]
            if (file) setPending({ garment: { file }, group: shopGroup, label: "Piece from a shop" })
            event.target.value = ""
          }}
        />
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
    </section>
  )
}
