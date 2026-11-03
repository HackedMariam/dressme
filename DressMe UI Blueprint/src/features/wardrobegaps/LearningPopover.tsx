import { useCallback, useRef, useState } from "react";
import { fetchLearning, resetRanker, retrainRanker, type LearningStatus } from "./api";
import { useDismiss } from "./useDismiss";

// What the ranker has learned from this user's answers ("I need this" / "Not relevant"), with the two actions.
// Each user has their own model: refreshing or resetting never affects anyone else.
export default function LearningPopover({ onChanged }: { onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<LearningStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(box, open, close);

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next) {
      setNote(null);
      fetchLearning().then(setStatus).catch((e: Error) => setNote({ text: e.message, error: true }));
    }
  };

  const run = async (action: () => Promise<LearningStatus>, done: string) => {
    setBusy(true);
    setNote(null);
    try {
      setStatus(await action());
      setNote({ text: done, error: false });
      onChanged(); // the ranking is reloaded with the new model
    } catch (e) {
      setNote({ text: (e as Error).message, error: true });
    } finally {
      setBusy(false);
    }
  };

  const refresh = () =>
    run(async () => {
      const result = await retrainRanker();
      return result.status;
    }, "Suggestions refreshed with your answers.");
  const reset = () => run(resetRanker, "Back to the general model.");

  const training = status?.last_training;
  return (
    <div ref={box} className="relative">
      <button
        onClick={toggle}
        aria-expanded={open}
        className="rounded-[10px] border border-[#E2E0D8] bg-white px-3.5 py-2 text-[13px] font-semibold hover:bg-[#FAF9F6]"
      >
        Learning
      </button>
      {open && (
        <div className="absolute right-0 top-[46px] z-30 w-[300px] rounded-xl border border-[#E2E0D8] bg-white p-4 shadow-[0_10px_28px_rgba(0,0,0,.12)]">
          <h4 className="font-display text-[15px] font-semibold text-[#1C1C1C]">Learning</h4>
          {!status && !note && <p className="mt-1 text-xs text-[#8C8A82]">Loading…</p>}
          {status && (
            <div className="mt-1 space-y-1 text-xs text-[#8C8A82]">
              <p>
                {status.feedback_labels === 0
                  ? "No answers yet."
                  : `${status.feedback_labels} answer${status.feedback_labels > 1 ? "s" : ""}: ${status.need_labels} “I need this”, ${status.not_relevant_labels} “Not relevant”.`}
              </p>
              <p>{status.personalised ? "Your ranking is personalised to you." : "Using the general model, trained on example data."}</p>
              {training && training.ndcg_at_3_before !== null && training.ndcg_at_3_after !== null && (
                <p>
                  Last refresh: ranking score {training.ndcg_at_3_before.toFixed(2)} → {training.ndcg_at_3_after.toFixed(2)}, measured on your own
                  answers (not a test on new data).
                </p>
              )}
            </div>
          )}
          <p className="mt-2 text-xs text-[#8C8A82]">Your answers adapt the ranking to you only.</p>
          {note && <p className={`mt-2 text-xs ${note.error ? "text-[#9A5A3C]" : "text-[#556B2F]"}`}>{note.text}</p>}
          <div className="mt-3 flex gap-1.5">
            <button
              onClick={refresh}
              disabled={busy || !status || status.feedback_labels === 0}
              className="rounded-[10px] bg-[#556B2F] px-3 py-2 text-[13px] font-semibold text-white hover:bg-[#6B8A3A] disabled:opacity-50"
            >
              {busy ? "Working…" : "Refresh suggestions"}
            </button>
            <button
              onClick={reset}
              disabled={busy || !status?.personalised}
              className="rounded-[10px] border border-[#E2E0D8] bg-white px-3 py-2 text-[13px] font-semibold hover:bg-[#FAF9F6] disabled:opacity-50"
            >
              Reset my model
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
