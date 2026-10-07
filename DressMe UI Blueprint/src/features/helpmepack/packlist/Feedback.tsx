import { useState } from "react"
import { CHANGE_OPTIONS, type Revision } from "../data"
import { Eyebrow, PrimaryButton, SecondaryButton } from "../ui"

export default function Feedback({
  coverage,
  combos,
  itemCount,
  revision,
  revisionReason,
  onBack,
  onViewPlan,
  onRegenerate,
}: {
  coverage: number
  combos: number
  itemCount: number
  revision: Revision | null
  revisionReason: string | null
  onBack: () => void
  onViewPlan: () => void
  onRegenerate: (reason: string) => void
}) {
  const [phase, setPhase] = useState<"rate" | "changes" | "thanks">("rate")
  const [reason, setReason] = useState<string | null>(null)

  if (revision) {
    return (
      <div className="space-y-6 max-w-3xl">
        <div className="bg-[#1C1C1C] rounded-xl p-8">
          <Eyebrow tone="olive">Updated packing plan</Eyebrow>
          <h2 className="font-display text-2xl font-medium text-white mt-2">
            Plan regenerated
          </h2>
          <p className="text-white/50 text-sm mt-1.5">
            Based on: {revisionReason} — {revision.summary}
          </p>

          <div className="grid grid-cols-3 gap-4 mt-6">
            {[
              { v: itemCount, l: "Items" },
              { v: revision.combos, l: "Combinations" },
              { v: `${revision.coverage}%`, l: "Coverage" },
            ].map((s) => (
              <div
                key={s.l}
                className="bg-white/5 border border-white/10 rounded-lg p-4 text-center"
              >
                <p className="font-display text-3xl font-semibold text-white leading-none">
                  {s.v}
                </p>
                <p className="text-white/40 text-[10px] uppercase tracking-widest mt-2">
                  {s.l}
                </p>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-[#E8EDE0] border border-[#556B2F]/20 rounded-xl px-6 py-4 flex items-center gap-3">
          <span className="text-[#556B2F] text-sm">✦</span>
          <p className="text-sm text-[#1C1C1C]">
            Your feedback was sent to your DressMe Stylist, who asked the
            Packing Agent to rebuild the set.
          </p>
        </div>

        <div className="flex items-center justify-between">
          <button
            onClick={() => setPhase("rate")}
            className="text-sm text-[#8C8A82] hover:text-[#1C1C1C]"
          >
            ← Back
          </button>
          <PrimaryButton onClick={onViewPlan}>
            View Updated Packing List →
          </PrimaryButton>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="bg-[#1C1C1C] rounded-xl p-8">
        <Eyebrow tone="olive">Your feedback</Eyebrow>

        {phase === "thanks" ? (
          <>
            <h2 className="font-display text-2xl font-medium text-white mt-2">
              Thanks — plan confirmed
            </h2>
            <p className="text-white/50 text-sm mt-1.5">
              Your Stylist will remember this for the next time you pack.
            </p>
            <div className="flex gap-3 mt-6">
              <PrimaryButton onClick={onViewPlan}>
                View My Packing List →
              </PrimaryButton>
              <button
                onClick={onBack}
                className="text-white/50 hover:text-white text-sm border border-white/20 rounded-lg px-5 py-3.5 transition-colors"
              >
                Back to coverage
              </button>
            </div>
          </>
        ) : (
          <>
            <h2 className="font-display text-2xl font-medium text-white mt-2">
              How does this packing plan feel?
            </h2>
            <div className="grid grid-cols-2 gap-4 mt-6">
              <button
                onClick={() => setPhase("thanks")}
                className="bg-white/5 hover:bg-white/10 border border-white/10 hover:border-[#556B2F] rounded-xl px-5 py-6 text-left transition-colors"
              >
                <span className="text-2xl">👍</span>
                <p className="text-white font-medium mt-3">Looks good</p>
                <p className="text-white/40 text-xs mt-1">
                  Lock this plan in for my trip
                </p>
              </button>
              <button
                onClick={() => setPhase("changes")}
                className="bg-white/5 hover:bg-white/10 border border-white/10 hover:border-[#556B2F] rounded-xl px-5 py-6 text-left transition-colors"
              >
                <span className="text-2xl">👎</span>
                <p className="text-white font-medium mt-3">I want changes</p>
                <p className="text-white/40 text-xs mt-1">
                  Tell your Stylist what to adjust
                </p>
              </button>
            </div>
          </>
        )}
      </div>

      {phase === "changes" && (
        <div className="bg-[#F0EFEA] rounded-xl p-7">
          <Eyebrow>What should we change?</Eyebrow>
          <div className="grid grid-cols-2 gap-3 mt-4">
            {CHANGE_OPTIONS.map((o) => (
              <label
                key={o}
                className={`flex items-center gap-3 bg-white border rounded-lg px-4 py-3 cursor-pointer transition-colors ${
                  reason === o
                    ? "border-[#556B2F] bg-[#E8EDE0]"
                    : "border-[#E2E0D8] hover:border-[#556B2F]/50"
                }`}
              >
                <input
                  type="radio"
                  name="change"
                  checked={reason === o}
                  onChange={() => setReason(o)}
                  className="accent-[#556B2F]"
                />
                <span className="text-sm text-[#1C1C1C]">{o}</span>
              </label>
            ))}
          </div>

          <div className="flex items-center justify-between mt-6">
            <p className="text-[11px] text-[#8C8A82]">
              Your feedback will be sent to your DressMe Stylist.
            </p>
            <PrimaryButton
              onClick={() => reason && onRegenerate(reason)}
              disabled={!reason}
            >
              Regenerate Plan →
            </PrimaryButton>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between">
        <button
          onClick={onBack}
          className="text-sm text-[#8C8A82] hover:text-[#1C1C1C]"
        >
          ← Back to coverage
        </button>
        {phase !== "changes" && (
          <SecondaryButton onClick={onViewPlan}>
            View My Packing List
          </SecondaryButton>
        )}
      </div>
    </div>
  )
}
