import type { Category, PackItem, Trip } from "../data"
import { Eyebrow, FlowFooter, PackedToggle, StatusBadge } from "../ui"

const ORDER: Category[] = [
  "TOPS",
  "BOTTOMS",
  "OUTERWEAR",
  "SHOES",
  "ACCESSORIES",
]

export default function PackList({
  trip,
  items,
  optionalItems,
  packed,
  onToggle,
  coverage,
  combos,
  purchaseState,
  revisionSummary,
  onBack,
  onNext,
  onOpenItem,
  onOpenPurchase,
  onEditTrip,
}: {
  trip: Trip
  items: PackItem[]
  optionalItems: PackItem[]
  packed: Record<string, boolean>
  onToggle: (id: string) => void
  coverage: number
  combos: number
  purchaseState: "pending" | "included" | "skipped"
  revisionSummary: string | null
  onBack: () => void
  onNext: () => void
  onOpenItem: (id: string) => void
  onOpenPurchase: () => void
  onEditTrip: () => void
}) {
  const packedCount = items.filter((i) => packed[i.id] !== false).length
  const grouped = ORDER.map((cat) => ({
    cat,
    list: items.filter((i) => i.category === cat),
  })).filter((g) => g.list.length > 0)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-[#1C1C1C] rounded-xl p-6 flex items-center justify-between gap-6">
        <div>
          <p className="text-[#556B2F] text-xs font-semibold uppercase tracking-widest">
            Pack List Ready
          </p>
          <h2 className="font-display text-2xl font-medium text-white mt-1">
            {trip.dest} · {trip.dates}
          </h2>
          <p className="text-white/50 text-sm mt-0.5">
            {trip.tripType} · {trip.dresscode} · {trip.bags}
          </p>
        </div>
        <button
          onClick={onEditTrip}
          className="text-white/50 hover:text-white text-xs border border-white/20 rounded-lg px-4 py-2 transition-colors"
        >
          Edit Trip
        </button>
      </div>

      {revisionSummary && (
        <div className="bg-[#E8EDE0] border border-[#556B2F]/20 rounded-xl px-5 py-3.5 flex items-center gap-3">
          <span className="text-[#556B2F] text-sm">↻</span>
          <p className="text-sm text-[#1C1C1C]">
            Plan regenerated from your feedback — {revisionSummary}
          </p>
        </div>
      )}

      {/* Hero summary */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { value: items.length, label: "Items", sub: "in your carry-on" },
          {
            value: combos,
            label: "Outfit combinations",
            sub: `from ${items.length} pieces`,
          },
          {
            value: `${coverage}%`,
            label: "Trip coverage",
            sub: "of your 7-day plan",
          },
        ].map((s) => (
          <div key={s.label} className="bg-[#F0EFEA] rounded-xl p-5">
            <p className="font-display text-4xl font-semibold text-[#1C1C1C] leading-none">
              {s.value}
            </p>
            <p className="text-xs uppercase tracking-widest text-[#8C8A82] mt-2">
              {s.label}
            </p>
            <p className="text-[11px] text-[#8C8A82] mt-0.5">{s.sub}</p>
          </div>
        ))}
      </div>

      {/* Gap banner */}
      {purchaseState === "pending" && (
        <button
          onClick={onOpenPurchase}
          className="w-full text-left bg-amber-50 border border-amber-200 rounded-xl px-5 py-4 flex items-center gap-4 hover:border-amber-400 transition-colors"
        >
          <span className="w-8 h-8 rounded-full bg-amber-100 text-amber-700 flex items-center justify-center text-sm shrink-0">
            ◆
          </span>
          <div>
            <p className="text-sm font-semibold text-amber-800">
              1 gap detected — no formal footwear in your wardrobe
            </p>
            <p className="text-xs text-amber-700/80 mt-0.5">
              Pointed-Toe Flats could complete your smart-casual dinners. Tap to
              review.
            </p>
          </div>
          <span className="ml-auto text-xs font-semibold text-amber-700 shrink-0">
            Review →
          </span>
        </button>
      )}

      {purchaseState === "skipped" && (
        <div className="bg-[#F0EFEA] border border-[#E2E0D8] rounded-xl px-5 py-3.5 flex items-center gap-3">
          <span className="text-[#8C8A82] text-sm">○</span>
          <p className="text-sm text-[#1C1C1C]">
            Pointed-Toe Flats skipped — coverage recalculated to {coverage}%.
            You can add it anytime.
          </p>
          <button
            onClick={onOpenPurchase}
            className="ml-auto text-xs font-semibold text-[#556B2F] hover:underline shrink-0"
          >
            Reconsider →
          </button>
        </div>
      )}

      {purchaseState === "included" && (
        <div className="bg-[#E8EDE0] border border-[#556B2F]/20 rounded-xl px-5 py-3.5 flex items-center gap-3">
          <span className="text-[#556B2F] text-sm">◆</span>
          <p className="text-sm text-[#1C1C1C]">
            Pointed-Toe Flats added to your plan as a recommended purchase —
            coverage {coverage}%.
          </p>
        </div>
      )}

      {/* Checklist */}
      <div className="bg-[#F0EFEA] rounded-xl overflow-hidden">
        <div className="px-6 py-4 border-b border-[#E2E0D8] flex items-center justify-between">
          <p className="font-medium text-[#1C1C1C] text-sm">Smart Checklist</p>
          <div className="flex items-center gap-4">
            <span className="text-xs text-[#8C8A82]">
              <span className="font-semibold text-[#1C1C1C]">
                {packedCount}
              </span>{" "}
              of {items.length} packed
            </span>
            <div className="w-24 h-1.5 bg-[#E2E0D8] rounded-full overflow-hidden">
              <div
                className="h-full bg-[#556B2F] rounded-full transition-all"
                style={{ width: `${(packedCount / items.length) * 100}%` }}
              />
            </div>
          </div>
        </div>

        {grouped.map((group) => (
          <div key={group.cat}>
            <div className="px-6 py-2 bg-[#E9E7E0] border-b border-[#E2E0D8]">
              <span className="text-[10px] font-semibold text-[#8C8A82] uppercase tracking-widest">
                {group.cat}
              </span>
            </div>
            {group.list.map((item) => (
              <div
                key={item.id}
                className="flex items-center gap-4 px-6 py-3 border-b border-[#E2E0D8] last:border-0 hover:bg-[#E2E0D8]/50 transition-colors"
              >
                <button
                  onClick={() => onOpenItem(item.id)}
                  className="w-10 h-12 rounded bg-[#E2E0D8] overflow-hidden shrink-0 hover:opacity-80 transition-opacity"
                  title={`Why ${item.name} was selected`}
                >
                  <img
                    src={item.img}
                    alt={item.name}
                    className="w-full h-full object-cover"
                  />
                </button>

                <button
                  onClick={() => onOpenItem(item.id)}
                  className="flex-1 min-w-0 text-left"
                >
                  <p className="text-sm font-medium text-[#1C1C1C] truncate">
                    {item.name}
                  </p>
                  <p className="text-[11px] text-[#8C8A82] truncate">
                    {item.meta} · {item.season}
                  </p>
                </button>

                <span className="text-xs text-[#8C8A82] shrink-0 w-20 text-right">
                  {item.outfits} outfits
                </span>
                <div className="shrink-0 w-[168px] flex justify-end">
                  <StatusBadge status={item.status} />
                </div>
                <PackedToggle
                  packed={packed[item.id] !== false}
                  onToggle={() => onToggle(item.id)}
                />
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* Optional extras */}
      <div className="bg-white border border-[#E2E0D8] rounded-xl p-6">
        <div className="flex items-center justify-between">
          <Eyebrow>Optional extras</Eyebrow>
          <span className="text-[11px] text-[#8C8A82]">
            Not counted in your {items.length} core items
          </span>
        </div>
        <div className="grid grid-cols-2 gap-4 mt-4">
          {optionalItems.map((item) => (
            <div
              key={item.id}
              className="flex items-center gap-4 bg-[#F0EFEA] rounded-lg p-3"
            >
              <button
                onClick={() => onOpenItem(item.id)}
                className="w-10 h-12 rounded bg-[#E2E0D8] overflow-hidden shrink-0 hover:opacity-80 transition-opacity"
              >
                <img
                  src={item.img}
                  alt={item.name}
                  className="w-full h-full object-cover"
                />
              </button>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-[#1C1C1C] truncate">
                  {item.name}
                </p>
                <p className="text-[11px] text-[#8C8A82]">{item.meta}</p>
              </div>
              <div className="flex flex-col items-end gap-2">
                <StatusBadge status={item.status} />
                <PackedToggle
                  packed={packed[item.id] === true}
                  onToggle={() => onToggle(item.id)}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      <FlowFooter
        onBack={onBack}
        backLabel="Back to optimizer"
        onNext={onNext}
        nextLabel="View Trip Coverage"
      />
    </div>
  )
}
