import { useMemo, useState } from "react"
import { asset } from "../../lib/api"
import { TAXONOMY, cap } from "../../lib/taxonomy"
import type { Page } from "../shell/navigation"
import { useWardrobe } from "../wardrobe/WardrobeProvider"
import { buildOutfits, currentSeason } from "./outfitBuilder"

const GROUP_ORDER = ["Outerwear", "Tops", "Dresses", "Bottoms", "Shoes"]

// Outfits composed from the user's own wardrobe for an occasion and a season.
export default function OutfitBuilderPage({ onNavigate }: { onNavigate: (page: Page) => void }) {
  const { items, loading } = useWardrobe()
  const [occasion, setOccasion] = useState("everyday")
  const [season, setSeason] = useState(currentSeason)
  const [seed, setSeed] = useState(0)

  const { outfits, missing } = useMemo(
    () => buildOutfits(items, { occasion, season }, 3, seed),
    [items, occasion, season, seed],
  )

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Outfit Builder</h1>
          <p className="mt-1 text-sm text-[#8C8A82]">
            Ready-to-wear outfits made only from the clothes you own.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={occasion}
            onChange={(event) => {
              setOccasion(event.target.value)
              setSeed(0)
            }}
            aria-label="Occasion"
            className="rounded-lg border border-[#E2E0D8] bg-white px-3 py-2 text-sm text-[#1C1C1C]"
          >
            {TAXONOMY.occasions.map((name) => (
              <option key={name} value={name}>
                {cap(name)}
              </option>
            ))}
          </select>
          <select
            value={season}
            onChange={(event) => {
              setSeason(event.target.value)
              setSeed(0)
            }}
            aria-label="Season"
            className="rounded-lg border border-[#E2E0D8] bg-white px-3 py-2 text-sm text-[#1C1C1C]"
          >
            {TAXONOMY.seasons.map((name) => (
              <option key={name} value={name}>
                {cap(name)}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => setSeed((value) => value + 1)}
            disabled={!outfits.length}
            className="rounded-lg bg-[#1C1C1C] px-4 py-2 text-sm font-semibold text-white hover:bg-[#333] disabled:opacity-40"
          >
            Shuffle
          </button>
        </div>
      </div>

      {loading && !items.length && (
        <div className="flex min-h-[240px] items-center justify-center text-sm text-[#8C8A82]">
          Loading your wardrobe...
        </div>
      )}

      {!loading && items.length < 3 && (
        <div className="rounded-xl border border-[#E2E0D8] bg-[#F0EFEA] px-6 py-10 text-center">
          <p className="font-medium text-[#1C1C1C]">Add a few more pieces first</p>
          <p className="mx-auto mt-1 max-w-sm text-sm text-[#8C8A82]">
            The builder needs at least a top, a bottom and shoes (or a dress) to compose an outfit.
          </p>
          <button
            type="button"
            onClick={() => onNavigate("wardrobe")}
            className="mt-4 rounded-lg bg-[#556B2F] px-4 py-2 text-xs font-semibold text-white hover:bg-[#6B8A3A]"
          >
            Add clothing
          </button>
        </div>
      )}

      {items.length >= 3 && outfits.length === 0 && (
        <div className="rounded-xl border border-[#E2E0D8] bg-[#F0EFEA] px-6 py-10 text-center text-sm text-[#8C8A82]">
          Your wardrobe cannot make a complete outfit yet. Missing: {missing.join(", ")}.
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        {outfits.map((outfit, index) => (
          <article key={outfit.items.map((item) => item.id).join()} className="rounded-xl border border-[#E2E0D8] bg-white p-4">
            <p className="text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">Outfit {index + 1}</p>
            <div className="mt-3 grid grid-cols-2 gap-2">
              {[...outfit.items]
                .sort((a, b) => GROUP_ORDER.indexOf(a.category_group) - GROUP_ORDER.indexOf(b.category_group))
                .map((item) => (
                  <div key={item.id} className="rounded-lg bg-[#F0EFEA] p-2">
                    <div className="flex aspect-[4/5] items-center justify-center overflow-hidden">
                      {item.cutout_url ? (
                        <img
                          src={asset(item.cutout_url)}
                          alt={item.name}
                          loading="lazy"
                          className="h-full w-full object-contain"
                        />
                      ) : null}
                    </div>
                    <p className="mt-1.5 truncate text-[11px] font-semibold text-[#1C1C1C]">{item.name}</p>
                    <p className="truncate text-[10px] text-[#8C8A82]">{cap(item.color_name ?? item.category)}</p>
                  </div>
                ))}
            </div>
            {outfit.why.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {outfit.why.map((reason) => (
                  <span key={reason} className="rounded-full bg-[#E8EDE0] px-2.5 py-1 text-[10px] font-semibold text-[#556B2F]">
                    {reason}
                  </span>
                ))}
              </div>
            )}
          </article>
        ))}
      </div>

      {missing.length > 0 && outfits.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-900">
          <span>Better outfits are possible: your wardrobe has no {missing.join(" or ")} for this occasion.</span>
          <button
            type="button"
            onClick={() => onNavigate("wardrobe-gaps")}
            className="rounded-lg bg-[#1C1C1C] px-3 py-1.5 text-xs font-semibold text-white hover:bg-black"
          >
            See what to buy
          </button>
        </div>
      )}
    </div>
  )
}
