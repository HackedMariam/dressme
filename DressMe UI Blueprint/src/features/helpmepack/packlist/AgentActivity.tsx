import { AGENT_FLOW } from "../data"

export default function AgentActivity({ onClose }: { onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-[70] overflow-y-auto"
      role="dialog"
      aria-label="Agent activity"
    >
      <div className="min-h-full bg-black/70 px-6 py-10 flex justify-center">
        <div className="w-full max-w-3xl">
          <div className="bg-[#1C1C1C] rounded-xl border border-white/10 overflow-hidden">
            <div className="px-7 py-6 border-b border-white/10 flex items-start justify-between gap-4">
              <div>
                <p className="text-[#556B2F] text-xs font-semibold uppercase tracking-widest">
                  ◇ Agent Activity
                </p>
                <h3 className="font-display text-2xl font-medium text-white mt-1.5">
                  Multi-agent exchange
                </h3>
                <p className="text-white/40 text-xs mt-1">
                  Technical view · prototype demonstration
                </p>
              </div>
              <button
                onClick={onClose}
                className="text-white/50 hover:text-white text-xs border border-white/20 rounded-lg px-4 py-2 transition-colors"
              >
                Close ×
              </button>
            </div>

            <div className="p-7">
              <div className="bg-white/5 border border-white/10 rounded-xl px-5 py-4 flex items-center justify-between">
                <div>
                  <p className="text-[#8FA968] text-[11px] uppercase tracking-widest">
                    Stylist Agent
                  </p>
                  <p className="text-white text-sm mt-1">
                    Request: “Create a packing plan for Paris, Oct 14–21.”
                  </p>
                </div>
                <span className="text-white/30 text-[10px] uppercase tracking-widest">
                  In
                </span>
              </div>

              {AGENT_FLOW.map((step, i) => (
                <div key={step.from}>
                  <p className="text-white/30 text-xs text-center py-2">
                    ↓ A2A
                  </p>
                  <div className="bg-white/5 border border-white/10 rounded-xl px-5 py-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-[#8FA968] text-[11px] uppercase tracking-widest">
                        A2A → {step.from}
                      </p>
                      <span className="text-white/25 text-[10px] uppercase tracking-widest">
                        {step.bo}
                      </span>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-4">
                      <div>
                        <p className="text-white/35 text-[10px] uppercase tracking-widest">
                          Request
                        </p>
                        <p className="text-white/85 text-sm mt-1 leading-snug">
                          “{step.request}”
                        </p>
                      </div>
                      <div>
                        <p className="text-white/35 text-[10px] uppercase tracking-widest">
                          Response
                        </p>
                        <p className="text-white text-sm mt-1 leading-snug font-medium">
                          {step.response}
                        </p>
                      </div>
                    </div>
                  </div>
                  {i === AGENT_FLOW.length - 1 && (
                    <p className="text-white/30 text-xs text-center py-2">↓</p>
                  )}
                </div>
              ))}

              <div className="bg-[#556B2F]/20 border border-[#556B2F]/50 rounded-xl px-5 py-4 mt-1">
                <p className="text-[#A8C078] text-[11px] uppercase tracking-widest">
                  Trust Agent
                </p>
                <div className="flex items-center justify-between mt-2">
                  <p className="text-white text-sm">Confidence: 91%</p>
                  <span className="text-[#A8C078] text-xs font-semibold">
                    ✓ Recommendation validated
                  </span>
                </div>
              </div>

              <p className="text-white/30 text-[11px] mt-5 leading-relaxed">
                This view is shown for demonstration only. In the product the
                same exchange happens behind a single, plain-language result.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
