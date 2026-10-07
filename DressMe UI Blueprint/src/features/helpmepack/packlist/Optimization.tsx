import { CORE_IDS, OPTIMIZER, REMOVED, byId } from "../data"
import { Eyebrow, FlowFooter } from "../ui"

export default function Optimization({
  onBack,
  onNext,
}: {
  onBack: () => void
  onNext: () => void
}) {
  return (
    <div className="space-y-6">
      <div>
        <Eyebrow>Optimizer result</Eyebrow>
        <h2 className="font-display text-3xl font-semibold text-[#1C1C1C] mt-1.5">
          Packing Optimized
        </h2>
      </div>

      <div className="grid grid-cols-[1fr_360px] gap-6">
        {/* Funnel */}
        <div className="bg-[#1C1C1C] rounded-xl p-7">
          <div className="bg-white/5 border border-white/10 rounded-lg px-5 py-4 flex items-center justify-between">
            <div>
              <p className="text-white/40 text-[11px] uppercase tracking-widest">
                Candidates
              </p>
              <p className="font-display text-xl text-white mt-0.5">
                {OPTIMIZER.candidates} candidate items
              </p>
            </div>
            <p className="font-display text-3xl text-white/70">
              {OPTIMIZER.candidates}
            </p>
          </div>

          <p className="text-center text-white/30 my-2">↓</p>

          <div className="bg-[#E8EDE0]/10 border border-[#556B2F]/40 rounded-lg px-5 py-4 flex items-center justify-between">
            <div>
              <p className="text-[#8FA968] text-[11px] uppercase tracking-widest">
                Redundancy pass
              </p>
              <p className="font-display text-xl text-white mt-0.5">
                {OPTIMIZER.removed} redundant items removed
              </p>
            </div>
            <p className="font-display text-3xl text-[#8FA968]">
              −{OPTIMIZER.removed}
            </p>
          </div>

          <p className="text-center text-white/30 my-2">↓</p>

          <div className="bg-[#556B2F] rounded-lg px-5 py-4 flex items-center justify-between">
            <div>
              <p className="text-white/60 text-[11px] uppercase tracking-widest">
                Essential set
              </p>
              <p className="font-display text-xl text-white mt-0.5">
                {OPTIMIZER.essential} essential items
              </p>
            </div>
            <p className="font-display text-3xl text-white">
              {OPTIMIZER.essential}
            </p>
          </div>

          <p className="text-white/50 text-sm leading-relaxed mt-5">
            DressMe selected the smallest set of items that can cover your trip
            while keeping enough outfit variety.
          </p>
        </div>

        {/* Stats + comparison */}
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-[#E8EDE0] rounded-xl p-5">
              <Eyebrow tone="olive">Saved</Eyebrow>
              <p className="font-display text-3xl font-semibold text-[#1C1C1C] mt-1.5">
                {OPTIMIZER.saved}
              </p>
              <p className="text-xs text-[#8C8A82] mt-1">luggage weight</p>
            </div>
            <div className="bg-[#F0EFEA] rounded-xl p-5">
              <Eyebrow>Combinations</Eyebrow>
              <p className="font-display text-3xl font-semibold text-[#1C1C1C] mt-1.5">
                {OPTIMIZER.combos}
              </p>
              <p className="text-xs text-[#8C8A82] mt-1">still available</p>
            </div>
          </div>

          <div className="bg-[#F0EFEA] rounded-xl p-5">
            <Eyebrow>Before / After</Eyebrow>
            <div className="mt-4 space-y-4">
              <div>
                <div className="flex items-center justify-between text-xs mb-1.5">
                  <span className="font-semibold text-[#1C1C1C]">
                    Before · 10 items
                  </span>
                  <span className="text-[#8C8A82]">100%</span>
                </div>
                <div className="h-2.5 bg-[#E2E0D8] rounded-full overflow-hidden">
                  <div className="h-full bg-[#8C8A82] rounded-full w-full" />
                </div>
              </div>
              <div>
                <div className="flex items-center justify-between text-xs mb-1.5">
                  <span className="font-semibold text-[#1C1C1C]">
                    After · 8 items
                  </span>
                  <span className="text-[#556B2F] font-semibold">80%</span>
                </div>
                <div className="h-2.5 bg-[#E2E0D8] rounded-full overflow-hidden">
                  <div
                    className="h-full bg-[#556B2F] rounded-full"
                    style={{ width: "80%" }}
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="bg-[#F0EFEA] rounded-xl p-5">
            <Eyebrow>Removed</Eyebrow>
            <div className="mt-3 space-y-3">
              {REMOVED.map((r) => {
                const item = byId(r.id)
                return (
                  <div
                    key={r.id}
                    className="flex items-center gap-3 opacity-55"
                  >
                    <div className="w-10 h-12 rounded bg-[#E2E0D8] overflow-hidden shrink-0 grayscale">
                      <img
                        src={item.img}
                        alt={item.name}
                        className="w-full h-full object-cover"
                      />
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-[#1C1C1C] line-through truncate">
                        {item.name}
                      </p>
                      <p className="text-[10px] text-[#8C8A82]">
                        {r.reason} · {r.detail}
                      </p>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white border border-[#E2E0D8] rounded-xl px-5 py-4 flex items-center gap-3 flex-wrap">
        <span className="text-[10px] font-semibold text-[#8C8A82] uppercase tracking-widest mr-1">
          Essential set
        </span>
        {CORE_IDS.map((id) => (
          <span
            key={id}
            className="text-[11px] bg-[#F0EFEA] border border-[#E2E0D8] text-[#1C1C1C] px-2.5 py-1 rounded-full"
          >
            {byId(id).name}
          </span>
        ))}
      </div>

      <FlowFooter
        onBack={onBack}
        backLabel="Back to looks"
        onNext={onNext}
        nextLabel="View My Packing List"
      />
    </div>
  )
}
