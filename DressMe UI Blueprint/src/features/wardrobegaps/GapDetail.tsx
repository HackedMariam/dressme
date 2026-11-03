import type { RankedGap, WebPhoto } from "./api";
import GapPhotos from "./GapPhotos";
import { FEATURES, PRIORITY_STYLE, reasonFor } from "./gapUtils";

// Everything about the selected missing piece. The main actions live in a bar under the scrolling content,
// so "I need this" is always visible whatever the screen height.
export default function GapDetail({
  goal,
  gap,
  currentCoverage,
  coverageAfter,
  confirmed,
  dismissed,
  onConfirm,
  onDismiss,
  onRestore,
  onAsk,
  onPhotosLoaded,
}: {
  goal: string;
  gap: RankedGap;
  currentCoverage: number;
  coverageAfter: number;
  confirmed: boolean;
  dismissed: boolean;
  onConfirm: () => void;
  onDismiss: () => void;
  onRestore: () => void;
  onAsk: () => void;
  onPhotosLoaded: (photos: WebPhoto[]) => void;
}) {
  const similar = Math.round(gap.redundancy_score * 100);
  const gain = Math.max(0, coverageAfter - currentCoverage);

  return (
    <section aria-label="Piece details" className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-[#E2E0D8] bg-white">
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={`rounded-md px-2 py-0.5 text-[11px] font-bold capitalize ${PRIORITY_STYLE[gap.priority]}`}>{gap.priority} priority</span>
          {confirmed && <span className="rounded-md bg-[#1C1C1C] px-2 py-0.5 text-[11px] font-bold text-white">I need this</span>}
          {dismissed && <span className="rounded-md bg-[#F0EFEA] px-2 py-0.5 text-[11px] font-bold text-[#8C8A82]">Not relevant</span>}
        </div>
        <h2 className="mt-1.5 font-display text-[27px] font-semibold leading-tight text-[#1C1C1C]">{gap.name}</h2>
        <p className="mt-1 text-[13px] text-[#8C8A82]">Suggested: {gap.suggested_item}</p>

        <GapPhotos key={`${goal}:${gap.candidate_id}`} goal={goal} candidateId={gap.candidate_id} onLoaded={onPhotosLoaded} />

        <p className="mt-4 text-sm leading-relaxed text-[#1C1C1C]">{reasonFor(gap)}</p>

        <div className="mt-4 grid grid-cols-3 gap-2.5">
          <div className="rounded-xl border border-[#CAD5C3] bg-[#E8EDE0] px-3 py-2.5 text-[#415638]">
            <b className="block font-display text-[22px] font-semibold">+{gap.pairable_owned_items}</b>
            <small className="mt-0.5 block text-[11px] leading-snug">owned pieces it combines with this season</small>
          </div>
          <div className="rounded-xl border border-[#E2E0D8] bg-[#FAF9F6] px-3 py-2.5">
            <b className="block font-display text-[22px] font-semibold">{gap.owned_count}/{gap.required_count}</b>
            <small className="mt-0.5 block text-[11px] leading-snug text-[#8C8A82]">
              {gap.matched_items.length ? `owned: ${gap.matched_items.join(", ")}` : "owned for this need"}
            </small>
          </div>
          <div className="rounded-xl border border-[#E2E0D8] bg-[#FAF9F6] px-3 py-2.5">
            <b className="block font-display text-[22px] font-semibold">{similar}%</b>
            <small className="mt-0.5 block text-[11px] leading-snug text-[#8C8A82]">
              {gap.redundancy_score >= 0.6
                ? `similar to your ${gap.closest_owned_item}: check it first`
                : `closest owned piece: ${gap.closest_owned_item}`}
            </small>
          </div>
        </div>

        <div className="mt-4">
          <div className="mb-1.5 flex justify-between text-xs text-[#8C8A82]">
            <span>Wardrobe coverage for this context</span>
            <span>
              {currentCoverage}% → <strong className="text-[#556B2F]">{coverageAfter}%</strong>
            </span>
          </div>
          <div
            className="relative h-2.5 overflow-hidden rounded-md bg-[#E2E0D8]"
            role="img"
            aria-label={`Coverage goes from ${currentCoverage}% to ${coverageAfter}% with this piece`}
          >
            <div className="absolute inset-y-0 left-0 bg-[#556B2F]" style={{ width: `${currentCoverage}%` }} />
            <div className="absolute inset-y-0 bg-[#9DBA72]" style={{ left: `${currentCoverage}%`, width: `${gain}%` }} />
          </div>
        </div>

        <details className="mt-4 border-t border-[#E2E0D8] pt-3">
          <summary className="cursor-pointer text-[13px] font-semibold text-[#556B2F]">Why this rank? · 6 criteria</summary>
          <div className="mt-2 space-y-2">
            {FEATURES.map((f) => {
              const value = gap[f.key] as number;
              return (
                <div key={f.label} className="grid grid-cols-[170px_1fr_38px] items-center gap-2.5 text-xs">
                  <span>{f.label}</span>
                  <span className="h-1.5 overflow-hidden rounded bg-[#E2E0D8]" aria-hidden="true">
                    <span className={`block h-full rounded ${f.inverse ? "bg-[#B08A5B]" : "bg-[#556B2F]"}`} style={{ width: `${Math.round(value * 100)}%` }} />
                  </span>
                  <em className="text-right not-italic text-[#8C8A82]">{value.toFixed(2)}</em>
                </div>
              );
            })}
          </div>
        </details>
      </div>

      <div className="flex shrink-0 flex-wrap items-center gap-2 border-t border-[#E2E0D8] bg-white px-6 py-3">
        <button
          onClick={onConfirm}
          aria-pressed={confirmed}
          className={`rounded-[10px] border px-3.5 py-2 text-[13px] font-semibold ${
            confirmed ? "border-[#1C1C1C] bg-[#1C1C1C] text-white" : "border-[#E2E0D8] bg-white text-[#1C1C1C] hover:bg-[#FAF9F6]"
          }`}
        >
          {confirmed ? "✓ I need this" : "I need this"}
        </button>
        <button
          onClick={dismissed ? onRestore : onDismiss}
          className="rounded-[10px] border border-[#E2E0D8] bg-white px-3.5 py-2 text-[13px] font-semibold text-[#1C1C1C] hover:bg-[#FAF9F6]"
        >
          {dismissed ? "Restore" : "Not relevant"}
        </button>
        <button onClick={onAsk} className="ml-auto rounded-[10px] bg-[#1C1C1C] px-3.5 py-2 text-[13px] font-semibold text-white hover:bg-black">
          Ask the agent →
        </button>
      </div>
    </section>
  );
}
