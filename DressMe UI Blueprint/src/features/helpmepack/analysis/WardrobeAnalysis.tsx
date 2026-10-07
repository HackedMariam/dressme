import { ITEMS, WARDROBE_STATS, byId } from "../data"
import { Eyebrow, FlowFooter, StatusBadge } from "../ui"

const MATCHED_IDS = [
  "blazer",
  "turtleneck",
  "trousers",
  "jeans",
  "oxford",
  "boots",
  "bag",
  "slipdress",
  "knit",
]

export default function WardrobeAnalysis({
  onBack,
  onNext,
  onOpenItem,
}: {
  onBack: () => void
  onNext: () => void
  onOpenItem: (id: string) => void
}) {
  return (
    <div className="space-y-6">
      <div className="bg-[#1C1C1C] rounded-xl p-6 flex items-end justify-between gap-8">
        <div>
          <Eyebrow tone="olive">Your Wardrobe</Eyebrow>
          <h2 className="font-display text-2xl font-medium text-white mt-2">
            {WARDROBE_STATS.total} items in your wardrobe
          </h2>
          <p className="text-white/50 text-sm mt-1">
            Only what you already own is used to build your pack.
          </p>
        </div>
        <div className="flex items-center gap-6 shrink-0">
          <div className="text-right">
            <p className="font-display text-4xl font-semibold text-white leading-none">
              {WARDROBE_STATS.matched}
            </p>
            <p className="text-white/40 text-[11px] uppercase tracking-widest mt-1.5">
              Match your trip
            </p>
          </div>
          <div className="w-px h-12 bg-white/10" />
          <div className="text-right">
            <p className="font-display text-4xl font-semibold text-[#8FA968] leading-none">
              29
            </p>
            <p className="text-white/40 text-[11px] uppercase tracking-widest mt-1.5">
              Not relevant
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {MATCHED_IDS.map((id) => {
          const item = byId(id)
          return (
            <button
              key={id}
              onClick={() => onOpenItem(id)}
              className="bg-[#F0EFEA] rounded-xl overflow-hidden text-left group cursor-pointer hover:shadow-md transition-shadow"
            >
              <div className="h-40 bg-[#E2E0D8] overflow-hidden relative">
                <img
                  src={item.img}
                  alt={item.name}
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                />
                <span className="absolute top-2 left-2 text-[9px] font-semibold bg-[#1C1C1C]/70 text-white px-2 py-0.5 rounded-full">
                  {item.season}
                </span>
              </div>
              <div className="p-3">
                <p className="text-[10px] text-[#8C8A82] font-medium uppercase tracking-wide">
                  {item.meta}
                </p>
                <p className="text-sm font-semibold text-[#1C1C1C] mt-0.5 leading-tight">
                  {item.name}
                </p>
                <div className="mt-2 pt-2 border-t border-[#E2E0D8]">
                  <StatusBadge status="own" />
                </div>
              </div>
            </button>
          )
        })}

        <div className="bg-[#F0EFEA] rounded-xl border border-[#E2E0D8] flex flex-col items-center justify-center text-center p-5">
          <span className="font-display text-3xl font-semibold text-[#1C1C1C]">
            +9
          </span>
          <p className="text-xs text-[#8C8A82] mt-1 leading-snug">
            more items match your trip conditions
          </p>
          <span className="text-[11px] font-semibold text-[#556B2F] mt-3">
            seen in the next step
          </span>
        </div>
      </div>

      <div className="flex items-center gap-4 bg-[#E8EDE0] border border-[#556B2F]/20 rounded-xl px-6 py-4">
        <span className="text-[#556B2F] text-lg leading-none">✦</span>
        <p className="text-sm text-[#1C1C1C]">
          DressMe matched your wardrobe to your destination, weather and style —
          nothing outside your closet is used unless it fills a real gap.
        </p>
        <span className="ml-auto text-[11px] text-[#8C8A82] shrink-0">
          {ITEMS.length} items reviewed in this demo
        </span>
      </div>

      <FlowFooter
        onBack={onBack}
        backLabel="Back to weather"
        onNext={onNext}
        nextLabel="Build Outfits"
      />
    </div>
  )
}
