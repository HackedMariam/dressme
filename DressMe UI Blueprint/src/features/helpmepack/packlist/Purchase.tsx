import { useState } from "react"
import { byId } from "../data"
import { Eyebrow, PrimaryButton, SecondaryButton, StatusBadge } from "../ui"

const STORES = [
  { name: "Massimo Dutti", price: "€59", match: "Best colour match" },
  { name: "ARKET", price: "€75", match: "Closest silhouette" },
  { name: "Zara", price: "€39", match: "Within budget" },
]

export default function Purchase({
  state,
  onClose,
  onInclude,
  onSkip,
}: {
  state: "pending" | "included" | "skipped"
  onClose: () => void
  onInclude: () => void
  onSkip: () => void
}) {
  const [showOptions, setShowOptions] = useState(false)
  const item = byId("flats")

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-6"
      role="dialog"
      aria-label="Purchase recommendation"
    >
      <div className="absolute inset-0 bg-black/45" onClick={onClose} />
      <div className="relative w-full max-w-2xl bg-[#FAF9F6] rounded-2xl overflow-hidden shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="bg-[#1C1C1C] px-7 py-5 flex items-center justify-between">
          <div>
            <p className="text-amber-400 text-xs font-semibold uppercase tracking-widest">
              One item may improve your plan
            </p>
            <p className="text-white/40 text-[11px] mt-1">
              Detected while optimizing your packing set
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-white/50 hover:text-white text-xl leading-none"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="p-7 space-y-5">
          <div className="flex gap-5">
            <div className="w-32 h-40 rounded-xl overflow-hidden bg-[#E2E0D8] shrink-0">
              <img
                src={item.img}
                alt={item.name}
                className="w-full h-full object-cover"
              />
            </div>
            <div className="min-w-0">
              <Eyebrow>Recommended</Eyebrow>
              <h3 className="font-display text-2xl font-medium text-[#1C1C1C] mt-1">
                {item.name}
              </h3>
              <div className="mt-2">
                <StatusBadge status="buy" />
              </div>
              <p className="text-sm text-[#1C1C1C] mt-3 leading-relaxed">
                <span className="font-semibold">Why?</span> No suitable formal
                footwear was found in your current wardrobe for smart-casual
                dinners.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            {[
              { l: "Used in", v: "3 outfits" },
              { l: "Compatible with", v: "4 existing garments" },
              { l: "Budget", v: "Within your profile budget" },
            ].map((s) => (
              <div key={s.l} className="bg-[#F0EFEA] rounded-lg p-4">
                <p className="text-[10px] font-semibold text-[#8C8A82] uppercase tracking-widest">
                  {s.l}
                </p>
                <p className="text-sm font-medium text-[#1C1C1C] mt-1.5 leading-snug">
                  {s.v}
                </p>
              </div>
            ))}
          </div>

          <div className="bg-[#E8EDE0] border border-[#556B2F]/20 rounded-xl px-5 py-4 flex items-center gap-3">
            <span className="text-[#556B2F] text-sm">✦</span>
            <p className="text-sm text-[#1C1C1C]">
              Adding it raises your trip coverage to 94%. Skipping it keeps your
              plan purchase-free at 89%.
            </p>
          </div>

          {showOptions && (
            <div className="bg-white border border-[#E2E0D8] rounded-xl overflow-hidden">
              <div className="px-5 py-3 border-b border-[#E2E0D8]">
                <Eyebrow>Purchase options</Eyebrow>
              </div>
              {STORES.map((s) => (
                <div
                  key={s.name}
                  className="flex items-center gap-4 px-5 py-3 border-b border-[#E2E0D8] last:border-0"
                >
                  <span className="text-sm font-medium text-[#1C1C1C] w-36">
                    {s.name}
                  </span>
                  <span className="text-xs text-[#8C8A82] flex-1">
                    {s.match}
                  </span>
                  <span className="text-sm font-semibold text-[#1C1C1C]">
                    {s.price}
                  </span>
                  <button
                    onClick={onInclude}
                    className="text-[11px] font-semibold bg-[#556B2F] hover:bg-[#6B8A3A] text-white px-3 py-1.5 rounded-lg transition-colors"
                  >
                    Add to plan
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="flex items-center justify-between gap-3 pt-1">
            <SecondaryButton onClick={onSkip}>
              {state === "skipped"
                ? "Keep it out of the plan"
                : "Continue Without It"}
            </SecondaryButton>
            {showOptions ? (
              <PrimaryButton onClick={onInclude}>Add to My Plan</PrimaryButton>
            ) : (
              <PrimaryButton onClick={() => setShowOptions(true)}>
                View Purchase Options
              </PrimaryButton>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
