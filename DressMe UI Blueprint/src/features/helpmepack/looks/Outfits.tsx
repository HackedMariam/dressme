import { LOOKS, OPTIMIZER, byId } from "../data"
import { Eyebrow, FlowFooter } from "../ui"

export default function Outfits({
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
          <Eyebrow tone="olive">Outfit Combinations</Eyebrow>
          <h2 className="font-display text-2xl font-medium text-white mt-2">
            Built only from pieces you own
          </h2>
          <p className="text-white/50 text-sm mt-1">
            Each look fits the weather, the activity and your dress code.
          </p>
        </div>
        <div className="flex items-end gap-7 shrink-0">
          <div className="text-right">
            <p className="font-display text-4xl font-semibold text-white leading-none">
              {OPTIMIZER.combos}
            </p>
            <p className="text-white/40 text-[11px] uppercase tracking-widest mt-1.5">
              Combinations
            </p>
          </div>
          <div className="text-right">
            <p className="font-display text-4xl font-semibold text-white leading-none">
              {OPTIMIZER.candidates}
            </p>
            <p className="text-white/40 text-[11px] uppercase tracking-widest mt-1.5">
              From items
            </p>
          </div>
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-3">
          <Eyebrow>Daily Looks</Eyebrow>
          <span className="text-[11px] text-[#8C8A82]">
            Scroll to see all {LOOKS.length} planned days →
          </span>
        </div>

        <div className="flex gap-4 overflow-x-auto pb-3 snap-x">
          {LOOKS.map((look) => {
            const items = look.itemIds.map(byId)
            return (
              <div
                key={look.id}
                className="w-[300px] shrink-0 snap-start bg-[#F0EFEA] rounded-xl overflow-hidden border border-[#E2E0D8] hover:border-[#556B2F]/40 transition-colors"
              >
                <div className="flex items-center justify-between px-4 py-3 border-b border-[#E2E0D8]">
                  <p className="text-xs font-semibold text-[#1C1C1C] uppercase tracking-widest">
                    {look.day} <span className="text-[#8C8A82]">·</span>{" "}
                    {look.occasion}
                  </p>
                  <span className="text-[10px] font-bold text-[#556B2F] bg-[#E8EDE0] px-2 py-0.5 rounded-full">
                    {look.compat}%
                  </span>
                </div>

                <div
                  className={`grid gap-px bg-[#E2E0D8] ${
                    items.length === 2 ? "grid-cols-2" : "grid-cols-3"
                  }`}
                >
                  {items.map((it) => (
                    <button
                      key={it.id}
                      onClick={() => onOpenItem(it.id)}
                      className="relative bg-[#E2E0D8] h-36 overflow-hidden group"
                      title={it.name}
                    >
                      <img
                        src={it.img}
                        alt={it.name}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                      />
                    </button>
                  ))}
                </div>

                <div className="p-4">
                  <p className="text-sm font-semibold text-[#1C1C1C] leading-snug">
                    {items.map((i) => i.name).join(" + ")}
                  </p>

                  <div className="mt-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] text-[#8C8A82] uppercase tracking-wide">
                        Compatibility
                      </span>
                      <span className="text-[11px] font-semibold text-[#1C1C1C]">
                        {look.compat}%
                      </span>
                    </div>
                    <div className="h-1.5 bg-[#E2E0D8] rounded-full overflow-hidden">
                      <div
                        className="h-full bg-[#556B2F] rounded-full"
                        style={{ width: `${look.compat}%` }}
                      />
                    </div>
                    <div className="flex items-center gap-1.5 pt-1">
                      <span className="text-[#556B2F] text-xs">✓</span>
                      <span className="text-[11px] text-[#1C1C1C]">
                        Weather suitable for 12–19°C
                      </span>
                    </div>
                  </div>

                  {look.note && (
                    <p className="text-[10px] text-[#8C8A82] mt-2.5 pt-2.5 border-t border-[#E2E0D8]">
                      ○ {look.note}
                    </p>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="flex items-center gap-4 bg-[#E8EDE0] border border-[#556B2F]/20 rounded-xl px-6 py-4">
        <span className="text-[#556B2F] text-lg leading-none">✦</span>
        <p className="text-sm text-[#1C1C1C]">
          {OPTIMIZER.combos} combinations generated from {OPTIMIZER.candidates}{" "}
          selected items — every look above is assembled from the same small
          set.
        </p>
      </div>

      <FlowFooter
        onBack={onBack}
        backLabel="Back to wardrobe"
        onNext={onNext}
        nextLabel="Optimize My Packing"
      />
    </div>
  )
}
