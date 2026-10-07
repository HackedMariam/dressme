import type { PackItem } from "../data"
import { LOOKS } from "../data"
import { Eyebrow, Stars, StatusBadge } from "../ui"

export default function ItemDetail({
  item,
  onClose,
}: {
  item: PackItem
  onClose: () => void
}) {
  const usedIn = LOOKS.filter((l) => l.itemIds.includes(item.id))

  return (
    <div
      className="fixed inset-0 z-[60] flex justify-end"
      role="dialog"
      aria-label={item.name}
    >
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-[520px] h-full bg-[#FAF9F6] overflow-y-auto shadow-2xl">
        <div className="relative h-64 bg-[#E2E0D8]">
          <img
            src={item.img}
            alt={item.name}
            className="w-full h-full object-cover"
          />
          <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-black/70 to-transparent" />
          <button
            onClick={onClose}
            className="absolute top-4 right-4 w-8 h-8 rounded-full bg-black/50 text-white hover:bg-black/70 transition-colors"
            aria-label="Close"
          >
            ×
          </button>
          <div className="absolute bottom-4 left-5 right-5">
            <p className="text-[11px] text-white/70 uppercase tracking-widest">
              {item.category}
            </p>
            <h3 className="font-display text-2xl font-medium text-white mt-0.5">
              {item.name}
            </h3>
          </div>
        </div>

        <div className="p-6 space-y-5">
          <div className="flex items-center justify-between gap-3">
            <StatusBadge status={item.status} />
            <span className="text-xs text-[#8C8A82]">
              {item.meta} · {item.season}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {[
              { l: "Used in", v: `${item.outfits} outfits` },
              { l: "Weather", v: `✓ ${item.weather}` },
              { l: "Style", v: `✓ ${item.style}` },
              { l: "Trip value", v: item.tripValue },
            ].map((r) => (
              <div key={r.l} className="bg-[#F0EFEA] rounded-lg p-3.5">
                <p className="text-[10px] font-semibold text-[#8C8A82] uppercase tracking-widest">
                  {r.l}
                </p>
                <p className="text-sm font-medium text-[#1C1C1C] mt-1 leading-snug">
                  {r.v}
                </p>
              </div>
            ))}
          </div>

          <div className="bg-[#E8EDE0] border border-[#556B2F]/20 rounded-xl p-5">
            <Eyebrow tone="olive">Why DressMe selected it</Eyebrow>
            <p className="text-sm text-[#1C1C1C] mt-2.5 leading-relaxed">
              {item.why}
            </p>
          </div>

          <div className="bg-[#F0EFEA] rounded-xl p-5">
            <Eyebrow>Selection scores</Eyebrow>
            <div className="mt-3.5 space-y-3">
              {[
                { l: "Versatility", v: item.stars.versatility },
                { l: "Weather suitability", v: item.stars.weather },
                { l: "Outfit compatibility", v: item.stars.compatibility },
              ].map((s) => (
                <div key={s.l} className="flex items-center justify-between">
                  <span className="text-sm text-[#1C1C1C]">{s.l}</span>
                  <Stars value={s.v} />
                </div>
              ))}
            </div>
          </div>

          {usedIn.length > 0 && (
            <div className="bg-white border border-[#E2E0D8] rounded-xl p-5">
              <Eyebrow>Used in these looks</Eyebrow>
              <div className="mt-3 space-y-2">
                {usedIn.map((l) => (
                  <div
                    key={l.id}
                    className="flex items-center justify-between text-xs"
                  >
                    <span className="text-[#1C1C1C] font-medium">
                      {l.day} · {l.occasion}
                    </span>
                    <span className="text-[#8C8A82]">
                      {l.compat}% compatibility
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <p className="text-[11px] text-[#8C8A82] flex items-center gap-2">
            <span className="text-[#556B2F]">◇</span>
            Recommendation validated by the Trust Agent · 91% confidence
          </p>
        </div>
      </div>
    </div>
  )
}
