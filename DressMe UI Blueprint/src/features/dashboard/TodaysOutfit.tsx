import { useMemo, useState } from "react"
import { asset } from "../../lib/api"
import { tryOnGroup } from "../../lib/pieces"
import { cap } from "../../lib/taxonomy"
import { buildOutfits, currentSeason } from "../outfits/outfitBuilder"
import type { Page } from "../shell/navigation"
import TryOnModal, { type OutfitTryOn } from "../shop/TryOnModal"
import { useWardrobe } from "../wardrobe/WardrobeProvider"

const GROUP_ORDER = ["Outerwear", "Tops", "Dresses", "Bottoms", "Shoes"]

// One ready-to-wear outfit for today, made from the user's own clothes, with a one-click virtual try-on.
export default function TodaysOutfit({ onNavigate }: { onNavigate: (page: Page) => void }) {
  const { items } = useWardrobe()
  const [seed, setSeed] = useState(0)
  const [tryOn, setTryOn] = useState<OutfitTryOn | null>(null)
  const season = currentSeason()

  const { outfits } = useMemo(
    () => buildOutfits(items, { occasion: "everyday", season }, 1, seed),
    [items, season, seed],
  )
  const outfit = outfits[0]
  if (!outfit) return null

  const pieces = [...outfit.items].sort(
    (a, b) => GROUP_ORDER.indexOf(a.category_group) - GROUP_ORDER.indexOf(b.category_group),
  )
  const wearable = pieces.filter((item) => tryOnGroup(item.category) && item.cutout_url)

  return (
    <section className="rounded-2xl border border-[#E2E0D8] bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#556B2F]">Today's outfit</p>
          <h2 className="mt-1 font-display text-xl font-medium text-[#1C1C1C]">
            An everyday look for {season}
          </h2>
        </div>
        <button
          type="button"
          onClick={() => setSeed((value) => value + 1)}
          className="rounded-lg border border-[#E2E0D8] px-3 py-1.5 text-xs font-semibold text-[#1C1C1C] hover:bg-[#F0EFEA]"
        >
          Another one
        </button>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {pieces.map((item) => (
          <div key={item.id} className="rounded-xl bg-[#F0EFEA] p-2.5">
            <div className="flex aspect-[4/5] items-center justify-center overflow-hidden">
              {item.cutout_url ? (
                <img src={asset(item.cutout_url)} alt={item.name} loading="lazy" className="h-full w-full object-contain" />
              ) : null}
            </div>
            <p className="mt-2 truncate text-xs font-semibold text-[#1C1C1C]">{item.name}</p>
            <p className="truncate text-[10px] text-[#8C8A82]">{cap(item.color_name ?? item.category)}</p>
          </div>
        ))}
      </div>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1.5">
          {outfit.why.map((reason) => (
            <span key={reason} className="rounded-full bg-[#E8EDE0] px-2.5 py-1 text-[10px] font-semibold text-[#556B2F]">
              {reason}
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          {wearable.length > 0 && (
            <button
              type="button"
              onClick={() =>
                setTryOn({
                  itemIds: wearable.map((item) => item.id),
                  previews: wearable.map((item) => asset(item.cutout_url)),
                })
              }
              className="rounded-lg bg-[#1C1C1C] px-4 py-2 text-xs font-semibold text-white hover:bg-black"
            >
              Virtual try-on
            </button>
          )}
          <button
            type="button"
            onClick={() => onNavigate("outfit-builder")}
            className="rounded-lg bg-[#556B2F] px-4 py-2 text-xs font-semibold text-white hover:bg-[#6B8A3A]"
          >
            More outfits
          </button>
        </div>
      </div>

      {tryOn && (
        <TryOnModal
          outfit={tryOn}
          label="Today's outfit on your avatar"
          onClose={() => setTryOn(null)}
          onOpenAvatar={() => onNavigate("avatar")}
        />
      )}
    </section>
  )
}
