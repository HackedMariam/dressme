import ScoreRing from "../../../components/ScoreRing"
import { COVERAGE_CHECKS, OPTIMIZER } from "../data"
import { Eyebrow, FlowFooter } from "../ui"

export default function Coverage({
  coverage,
  combos,
  itemCount,
  unpacked,
  purchaseState,
  onBack,
  onNext,
  onReview,
  onOpenPurchase,
}: {
  coverage: number
  combos: number
  itemCount: number
  unpacked: number
  purchaseState: "pending" | "included" | "skipped"
  onBack: () => void
  onNext: () => void
  onReview: () => void
  onOpenPurchase: () => void
}) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-[380px_1fr] gap-6">
        {/* Score */}
        <div className="bg-[#1C1C1C] rounded-xl p-7 flex flex-col items-center justify-center text-center">
          <Eyebrow tone="olive">Your Trip Coverage</Eyebrow>
          <div className="relative mt-5">
            <ScoreRing
              score={coverage}
              size={200}
              track="rgba(255,255,255,0.12)"
            />
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="font-display text-5xl font-semibold text-white">
                {coverage}%
              </span>
              <span className="text-white/40 text-[10px] uppercase tracking-widest mt-1">
                Coverage
              </span>
            </div>
          </div>
          <p className="text-white/50 text-sm mt-5 leading-relaxed">
            {itemCount} items are enough to create {combos} suitable
            combinations for your trip.
          </p>
        </div>

        {/* Breakdown */}
        <div className="space-y-4">
          <div className="bg-[#F0EFEA] rounded-xl p-6">
            <Eyebrow>What is covered</Eyebrow>
            <div className="mt-4 space-y-2.5">
              {COVERAGE_CHECKS.map((c, i) => (
                <div key={c.label} className="flex items-center gap-3">
                  <span className="w-5 h-5 rounded-full bg-[#E8EDE0] text-[#556B2F] text-[11px] font-bold flex items-center justify-center shrink-0">
                    ✓
                  </span>
                  <span className="text-sm text-[#1C1C1C]">{c.label}</span>
                  <span className="ml-auto text-xs font-semibold text-[#556B2F]">
                    {i === 4 ? combos : c.value}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-[#E8EDE0] border border-[#556B2F]/20 rounded-xl p-5">
            <Eyebrow tone="olive">How it is measured</Eyebrow>
            <div className="flex items-center justify-between gap-2 mt-4">
              {[
                { v: itemCount, l: "garments" },
                { v: combos, l: "combinations" },
                { v: `${coverage}%`, l: "coverage" },
              ].map((n, i) => (
                <div key={n.l} className="flex items-center gap-2 flex-1">
                  <div className="flex-1 bg-white border border-[#E2E0D8] rounded-lg py-3 text-center">
                    <p className="font-display text-2xl font-semibold text-[#1C1C1C] leading-none">
                      {n.v}
                    </p>
                    <p className="text-[10px] uppercase tracking-widest text-[#8C8A82] mt-1.5">
                      {n.l}
                    </p>
                  </div>
                  {i < 2 && <span className="text-[#8C8A82]">↓</span>}
                </div>
              ))}
            </div>
            <p className="text-[11px] text-[#8C8A82] mt-3.5">
              Coverage can change if you remove an item — try unchecking a piece
              in your pack list.
            </p>
          </div>
        </div>
      </div>

      {/* Statuses */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white border border-[#E2E0D8] rounded-xl p-5">
          <Eyebrow>Optimizer</Eyebrow>
          <p className="text-sm text-[#1C1C1C] mt-2">
            {OPTIMIZER.removed} redundant items removed · saved{" "}
            {OPTIMIZER.saved}
          </p>
        </div>
        <div className="bg-white border border-[#E2E0D8] rounded-xl p-5">
          <Eyebrow>Luggage</Eyebrow>
          <p className="text-sm text-[#1C1C1C] mt-2">
            1 carry-on · {itemCount} items · under the limit
          </p>
        </div>
        <button
          onClick={onOpenPurchase}
          className="bg-white border border-[#E2E0D8] rounded-xl p-5 text-left hover:border-[#556B2F] transition-colors"
        >
          <Eyebrow>Gap detected</Eyebrow>
          <p className="text-sm text-[#1C1C1C] mt-2">
            {purchaseState === "included"
              ? "Pointed-Toe Flats included"
              : purchaseState === "skipped"
                ? "Pointed-Toe Flats declined"
                : "Formal footwear missing — review"}
          </p>
        </button>
      </div>

      {unpacked > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-5 py-3.5 flex items-center gap-3">
          <span className="text-amber-700 text-sm">!</span>
          <p className="text-sm text-amber-800">
            {unpacked} item{unpacked > 1 ? "s are" : " is"} marked as not packed
            — coverage dropped to {coverage}%.
          </p>
        </div>
      )}

      <FlowFooter
        onBack={onBack}
        backLabel="Back to pack list"
        onNext={onNext}
        nextLabel="Rate This Plan"
      />
      <div className="flex justify-center -mt-3">
        <button
          onClick={onReview}
          className="text-xs font-semibold text-[#556B2F] hover:underline"
        >
          ← Review my items first
        </button>
      </div>
    </div>
  )
}
