import { useEffect, useRef, useState } from "react"
import { useWardrobe } from "../wardrobe/WardrobeProvider"
import { fetchGaps } from "../wardrobegaps/api"
import { SHOP_GOAL_KEY } from "./OutfitsToBuy"

type Note = { added: number; missing: string[] }

const SETTLE_MS = 2000 // wait for the end of a batch of additions before looking at what is missing
const VISIBLE_MS = 15000

function rememberedGoal() {
  try {
    return localStorage.getItem(SHOP_GOAL_KEY) || "winter_work"
  } catch {
    return "winter_work"
  }
}

// A notification each time items are added to the wardrobe: what is still missing, with a link to the shops.
export default function ShopNotifications({ onOpen }: { onOpen: () => void }) {
  const { items, loading } = useWardrobe()
  const known = useRef<number | null>(null)
  const [note, setNote] = useState<Note | null>(null)

  useEffect(() => {
    if (loading) return
    if (known.current === null) {
      known.current = items.length // the first load is not an addition
      return
    }
    const added = items.length - known.current
    known.current = items.length
    if (added <= 0) return

    let cancelled = false
    const timer = setTimeout(() => {
      fetchGaps(rememberedGoal())
        .then((ranking) => {
          if (cancelled) return
          const missing = ranking.ranked_gaps.slice(0, 3).map((gap) => gap.suggested_item || gap.name)
          if (missing.length) setNote({ added, missing })
        })
        .catch(() => {}) // a notification is a bonus: stay silent if the suggestion service is not running
    }, SETTLE_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [items.length, loading])

  useEffect(() => {
    if (!note) return
    const timer = setTimeout(() => setNote(null), VISIBLE_MS)
    return () => clearTimeout(timer)
  }, [note])

  if (!note) return null

  return (
    <div
      role="status"
      className="fixed bottom-6 right-6 z-40 w-80 rounded-2xl border border-[#E2E0D8] bg-white p-4 shadow-xl"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-[#1C1C1C]">
            {note.added} new item{note.added === 1 ? "" : "s"} in your wardrobe
          </p>
          <p className="mt-0.5 text-xs text-[#8C8A82]">You may still want to add:</p>
        </div>
        <button
          type="button"
          onClick={() => setNote(null)}
          aria-label="Dismiss"
          className="text-sm text-[#8C8A82] hover:text-[#1C1C1C]"
        >
          {"✕"}
        </button>
      </div>
      <ul className="mt-2 space-y-1">
        {note.missing.map((piece) => (
          <li key={piece} className="flex items-center gap-2 text-sm capitalize text-[#1C1C1C]">
            <span className="h-1.5 w-1.5 rounded-full bg-[#556B2F]" />
            {piece}
          </li>
        ))}
      </ul>
      <button
        type="button"
        onClick={() => {
          setNote(null)
          onOpen()
        }}
        className="mt-3 w-full rounded-lg bg-[#556B2F] px-3 py-2 text-xs font-semibold text-white hover:bg-[#6B8A3A]"
      >
        See them in Tunisian shops
      </button>
    </div>
  )
}
