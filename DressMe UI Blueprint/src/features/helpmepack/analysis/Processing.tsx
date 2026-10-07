import { useEffect, useState } from "react"
import { PROCESS_TASKS } from "../data"
import { Eyebrow, PrimaryButton, SecondaryButton } from "../ui"

export default function Processing({
  onBack,
  onNext,
  onOpenAgents,
}: {
  onBack: () => void
  onNext: () => void
  onOpenAgents: () => void
}) {
  const [done, setDone] = useState(0)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (done >= PROCESS_TASKS.length) return
    const t = setTimeout(() => setDone((d) => d + 1), 520)
    return () => clearTimeout(t)
  }, [done])

  const complete = done >= PROCESS_TASKS.length
  const pct = Math.round((done / PROCESS_TASKS.length) * 100)

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="bg-[#1C1C1C] rounded-xl p-8">
        <div className="flex items-start justify-between gap-6">
          <div>
            <Eyebrow tone="olive">Building your packing plan</Eyebrow>
            <h2 className="font-display text-2xl font-medium text-white mt-2">
              {complete ? "Your plan is ready" : "Working through your trip…"}
            </h2>
            <p className="text-white/45 text-sm mt-1.5">
              {complete
                ? "10 candidates optimized into 8 essential items."
                : "Each step uses a different part of DressMe."}
            </p>
          </div>
          <div className="text-right shrink-0">
            <p className="font-display text-3xl font-semibold text-white leading-none">
              {pct}%
            </p>
            <p className="text-white/40 text-[10px] uppercase tracking-widest mt-1">
              Progress
            </p>
          </div>
        </div>

        <div className="h-1.5 bg-white/10 rounded-full overflow-hidden mt-5">
          <div
            className="h-full bg-[#556B2F] rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>

        <div className="mt-6 space-y-1">
          {PROCESS_TASKS.map((task, i) => {
            const isDone = i < done
            const isActive = i === done && !complete
            return (
              <div
                key={task}
                className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                  isActive ? "bg-white/5" : ""
                }`}
              >
                <span
                  className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 ${
                    isDone
                      ? "bg-[#556B2F] text-white"
                      : isActive
                        ? "bg-[#556B2F]/25 text-[#8FA968]"
                        : "bg-white/10 text-white/30"
                  }`}
                >
                  {isDone ? "✓" : isActive ? "●" : "○"}
                </span>
                <span
                  className={`text-sm ${
                    isDone
                      ? "text-white/85"
                      : isActive
                        ? "text-white"
                        : "text-white/35"
                  }`}
                >
                  {task}
                </span>
                {isActive && (
                  <span className="ml-auto text-[10px] uppercase tracking-widest text-[#8FA968] animate-pulse">
                    Running
                  </span>
                )}
                {isDone && (
                  <span className="ml-auto text-[10px] text-white/25 uppercase tracking-widest">
                    Done
                  </span>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* How DressMe works */}
      <div className="bg-[#F0EFEA] rounded-xl overflow-hidden">
        <button
          onClick={() => setOpen(!open)}
          className="w-full flex items-center justify-between px-6 py-4"
        >
          <span className="text-xs font-semibold text-[#8C8A82] uppercase tracking-widest">
            How DressMe works
          </span>
          <span className="text-[#556B2F] text-sm">
            {open ? "− Hide" : "+ Expand"}
          </span>
        </button>

        {open && (
          <div className="px-6 pb-6">
            <div className="bg-white border border-[#E2E0D8] rounded-xl p-5">
              <div className="text-center">
                <p className="text-xs font-semibold text-[#1C1C1C] uppercase tracking-widest">
                  Stylist Agent
                </p>
                <p className="text-[11px] text-[#8C8A82] mt-1">
                  Understands your request and routes it
                </p>
              </div>
              <p className="text-center text-[#8C8A82] my-2">↓</p>
              <div className="grid grid-cols-4 gap-2">
                {["Wardrobe", "Outfit", "Gap", "Packing"].map((a) => (
                  <div
                    key={a}
                    className="bg-[#F0EFEA] border border-[#E2E0D8] rounded-lg py-3 text-center"
                  >
                    <p className="text-xs font-semibold text-[#1C1C1C]">{a}</p>
                    <p className="text-[10px] text-[#8C8A82] mt-0.5">Agent</p>
                  </div>
                ))}
              </div>
              <p className="text-center text-[#8C8A82] my-2">↓</p>
              <div className="text-center">
                <p className="text-xs font-semibold text-[#556B2F] uppercase tracking-widest">
                  Optimized recommendation
                </p>
                <p className="text-[11px] text-[#8C8A82] mt-1">
                  Checked by the Trust Agent before it reaches you
                </p>
              </div>
            </div>

            <button
              onClick={onOpenAgents}
              className="mt-4 text-xs font-semibold text-[#556B2F] hover:underline"
            >
              Open the full Agent Activity view →
            </button>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between gap-4">
        <button
          onClick={onBack}
          className="text-sm text-[#8C8A82] hover:text-[#1C1C1C] transition-colors"
        >
          ← Back to wardrobe
        </button>
        <div className="flex items-center gap-3">
          {complete ? (
            <PrimaryButton onClick={onNext}>
              See My Outfit Combinations →
            </PrimaryButton>
          ) : (
            <SecondaryButton onClick={onNext}>Continue</SecondaryButton>
          )}
        </div>
      </div>
    </div>
  )
}
