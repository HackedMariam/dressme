import { useEffect, useRef, useState } from "react";
import type { CoveredRequirement, RankedGap } from "./api";
import { PRIORITY_STYLE } from "./gapUtils";

function Thumb({ url }: { url?: string }) {
  return (
    <span className="grid h-[46px] w-[46px] shrink-0 place-items-center overflow-hidden rounded-[10px] bg-[#F0EFEA] text-lg text-[#556B2F]" aria-hidden="true">
      {url ? <img src={url} alt="" loading="lazy" referrerPolicy="no-referrer" className="h-full w-full object-cover" /> : "◐"}
    </span>
  );
}

function ListSkeleton() {
  return (
    <div className="space-y-2 p-3" aria-label="Analysing your wardrobe">
      {[0, 1, 2, 3, 4].map((i) => (
        <div key={i} className="h-[62px] animate-pulse rounded-xl bg-[#F0EFEA]" />
      ))}
    </div>
  );
}

// The ranked missing pieces, one compact row each: the first ones are visible without scrolling.
// A piece the user dismissed stays in place (dimmed), so ranks never jump around.
export default function GapList({
  gaps,
  covered,
  selectedId,
  isDismissed,
  isConfirmed,
  thumbs,
  onSelect,
}: {
  gaps: RankedGap[] | null;
  covered: CoveredRequirement[];
  selectedId: string | null;
  isDismissed: (id: string) => boolean;
  isConfirmed: (id: string) => boolean;
  thumbs: Record<string, string>;
  onSelect: (id: string) => void;
}) {
  const [coveredOpen, setCoveredOpen] = useState(false);
  const selectedRow = useRef<HTMLButtonElement>(null);
  const open = gaps?.filter((g) => !isDismissed(g.candidate_id)).length ?? 0;

  // Keyboard navigation moves the selection: keep the selected row in view.
  useEffect(() => {
    selectedRow.current?.scrollIntoView({ block: "nearest" });
  }, [selectedId]);

  return (
    <section aria-label="Missing pieces" className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-[#E2E0D8] bg-white">
      <div className="flex items-baseline justify-between px-4 pb-2 pt-3.5">
        <h2 className="font-display text-[17px] font-semibold text-[#1C1C1C]">Missing pieces</h2>
        <small className="text-[11.5px] text-[#8C8A82]">{gaps ? `${open} to consider` : "Analysing…"}</small>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
        {!gaps && <ListSkeleton />}
        {gaps && gaps.length === 0 && (
          <p className="px-3 py-6 text-center text-xs text-[#8C8A82]">Nothing is missing for this context.</p>
        )}
        <ul className="space-y-0.5">
          {gaps?.map((gap, index) => {
            const selected = gap.candidate_id === selectedId;
            const dismissed = isDismissed(gap.candidate_id);
            return (
              <li key={gap.candidate_id}>
                <button
                  ref={selected ? selectedRow : undefined}
                  onClick={() => onSelect(gap.candidate_id)}
                  aria-current={selected ? "true" : undefined}
                  className={`relative grid w-full grid-cols-[22px_1fr_46px] items-center gap-2.5 rounded-xl border px-2 py-2.5 text-left transition-colors ${
                    selected ? "border-[#CAD5C3] bg-[#E8EDE0]" : "border-transparent hover:bg-[#FAF9F6]"
                  } ${dismissed ? "opacity-50" : ""}`}
                >
                  {selected && <span aria-hidden="true" className="absolute bottom-3 left-[-1px] top-3 w-[3px] rounded bg-[#556B2F]" />}
                  <span className="text-center font-display text-[17px] text-[#8C8A82]">{index + 1}</span>
                  <span className="min-w-0">
                    <span className="flex flex-wrap items-center gap-1.5">
                      <span className={`text-[13.5px] font-semibold text-[#1C1C1C] ${dismissed ? "line-through" : ""}`}>{gap.name}</span>
                      <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-bold capitalize ${PRIORITY_STYLE[gap.priority]}`}>{gap.priority}</span>
                      {isConfirmed(gap.candidate_id) && <span className="rounded-md bg-[#1C1C1C] px-1.5 py-0.5 text-[10px] font-bold text-white">needed</span>}
                    </span>
                    <span className="mt-1.5 flex items-center gap-2 text-[11px] text-[#8C8A82]">
                      <span className="h-[5px] max-w-[120px] flex-1 overflow-hidden rounded bg-[#E2E0D8]" aria-hidden="true">
                        <span
                          className="block h-full rounded bg-[#556B2F]"
                          style={{ width: `${gap.required_count ? Math.min(100, (gap.owned_count / gap.required_count) * 100) : 0}%` }}
                        />
                      </span>
                      {gap.owned_count}/{gap.required_count} owned
                    </span>
                  </span>
                  <Thumb url={thumbs[gap.candidate_id]} />
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="border-t border-[#E2E0D8] px-4 py-2.5 text-[12.5px]">
        <button
          onClick={() => setCoveredOpen((o) => !o)}
          aria-expanded={coveredOpen}
          className="flex w-full items-center justify-between font-semibold text-[#556B2F]"
        >
          <span>✓ {covered.length} need{covered.length === 1 ? "" : "s"} covered</span>
          <span aria-hidden="true">{coveredOpen ? "▴" : "▾"}</span>
        </button>
        {coveredOpen && (
          <ul className="mt-2.5 flex max-h-32 flex-wrap gap-1.5 overflow-y-auto">
            {covered.map((c) => (
              <li
                key={c.candidate_id}
                title={`Covered by ${c.matched_items.join(", ")}`}
                className="rounded-full bg-[#E8EDE0] px-2.5 py-1 text-[11.5px] text-[#415638]"
              >
                {c.name} {c.owned_count}/{c.required_count}
              </li>
            ))}
            {covered.length === 0 && <li className="text-xs text-[#8C8A82]">No need is fully covered yet for this context.</li>}
          </ul>
        )}
      </div>
    </section>
  );
}
