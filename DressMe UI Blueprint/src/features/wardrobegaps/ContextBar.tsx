import { useCallback, useRef, useState } from "react";
import type { GapRanking, Goal } from "./api";
import { GOAL_DESIGN } from "./gapUtils";
import LearningPopover from "./LearningPopover";
import { useDismiss } from "./useDismiss";

function CoverageRing({ score }: { score: number | null }) {
  return (
    <div
      className="grid h-[46px] w-[46px] shrink-0 place-items-center rounded-full"
      style={{ background: `conic-gradient(#556B2F ${(score ?? 0) * 3.6}deg, #E2E0D8 0)` }}
      role="img"
      aria-label={`Wardrobe coverage: ${score === null ? "loading" : `${score}%`}`}
    >
      <span className="grid h-9 w-9 place-items-center rounded-full bg-white text-xs font-bold text-[#1C1C1C]">
        {score === null ? "—" : `${score}%`}
      </span>
    </div>
  );
}

const DEPARTMENT_LABEL = { women: "Women’s wardrobe", men: "Men’s wardrobe", both: "Women’s & men’s wardrobe" } as const;

// One compact card instead of a title, four stat tiles and a wall of context cards:
// title and tools on the first row, the contexts as pills on the second.
export default function ContextBar({
  goals,
  goal,
  onGoal,
  score,
  department,
  onAsk,
  onRankingChanged,
}: {
  goals: Goal[];
  goal: string;
  onGoal: (id: string) => void;
  score: number | null;
  department?: GapRanking["department"];
  onAsk: () => void;
  onRankingChanged: () => void;
}) {
  const [tipOpen, setTipOpen] = useState(false);
  const tip = useRef<HTMLDivElement>(null);
  const closeTip = useCallback(() => setTipOpen(false), []);
  useDismiss(tip, tipOpen, closeTip);

  return (
    <section aria-label="Context and tools" className="rounded-2xl border border-[#E2E0D8] bg-white px-5 py-3.5">
      <div className="flex items-center gap-3">
        <div className="mr-auto min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-[1.6px] text-[#556B2F]">
            BO3 · Wardrobe Gaps
            {department && (
              <span className="ml-2 rounded-full bg-[#E8EDE0] px-2 py-0.5 text-[10px] normal-case tracking-normal text-[#415638]">
                {DEPARTMENT_LABEL[department]}
              </span>
            )}
          </p>
          <h1 className="font-display text-[22px] font-semibold leading-tight text-[#1C1C1C]">Wardrobe Gaps</h1>
        </div>

        <div ref={tip} className="relative flex items-center gap-2">
          <CoverageRing score={score} />
          <button
            onClick={() => setTipOpen((o) => !o)}
            aria-label="How is coverage calculated?"
            aria-expanded={tipOpen}
            className="h-5 w-5 rounded-full border border-[#E2E0D8] bg-[#FAF9F6] text-[11px] font-bold leading-none text-[#8C8A82] hover:text-[#1C1C1C]"
          >
            i
          </button>
          {tipOpen && (
            <div role="tooltip" className="absolute right-0 top-[54px] z-30 w-[320px] rounded-[10px] bg-[#1C1C1C] p-3.5 text-xs leading-relaxed text-[#EEE] shadow-[0_8px_24px_rgba(0,0,0,.2)]">
              Coverage rules decide whether a gap exists: each context lists the pieces it needs and how many. Coverage is the share of
              needed pieces you already own. Missing pieces are then ordered by a learning-to-rank model using six criteria (open “Why this
              rank?” on a piece). The model starts from example data and adapts to your answers.
            </div>
          )}
        </div>

        <LearningPopover onChanged={onRankingChanged} />
        <button
          onClick={onAsk}
          className="inline-flex shrink-0 items-center gap-2 rounded-[10px] bg-[#556B2F] px-4 py-2 text-[13px] font-semibold text-white hover:bg-[#6B8A3A]"
        >
          ✦ Plan my purchases
        </button>
      </div>

      <div role="group" aria-label="What are you dressing for?" className="mt-3 flex flex-wrap gap-1.5">
        {goals.map((g) => {
          const on = g.id === goal;
          const design = GOAL_DESIGN[g.id];
          return (
            <button
              key={g.id}
              aria-pressed={on}
              onClick={() => onGoal(g.id)}
              title={design ? `${g.label} · ${design.note}` : g.label}
              className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-3 py-1.5 text-[12.5px] transition-colors ${
                on
                  ? "border-[#556B2F] bg-[#556B2F] font-semibold text-white"
                  : "border-[#E2E0D8] bg-[#FAF9F6] font-medium text-[#1C1C1C] hover:border-[#556B2F]"
              }`}
            >
              <span aria-hidden="true" className="text-[13px]">{design?.icon ?? "◐"}</span>
              {design?.short ?? g.label}
            </button>
          );
        })}
      </div>
    </section>
  );
}
