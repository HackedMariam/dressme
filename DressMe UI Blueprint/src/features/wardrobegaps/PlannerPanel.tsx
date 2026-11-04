import { useEffect, useRef, useState } from "react";
import { fetchPlan, type PlanPurchase, type PlanResult } from "./api";
import { GOAL_DESIGN } from "./gapUtils";
import PlanPhotos from "./PlanPhotos";

// The six things the agent does, in order. The backend returns what each one really found (PlanResult.steps, same ids);
// the interface plays them back one by one so the user sees an agent at work instead of a spinner.
const STEPS = [
  { id: "understand", title: "Understanding your goal" },
  { id: "analyse", title: "Analysing your wardrobe" },
  { id: "combine", title: "Finding pieces that close several needs" },
  { id: "budget", title: "Fitting the budget" },
  { id: "compare", title: "Comparing with the simple method" },
  { id: "write", title: "Writing the plan" },
] as const;

const EXAMPLES = [
  "A summer wedding and a winter internship, 300 TND",
  "Gym, hiking and everyday basics",
  "Dinner dates this month, budget 200 TND",
];

const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function Spinner() {
  return <span className="h-4 w-4 animate-spin rounded-full border-2 border-[#CAD5C3] border-t-[#556B2F]" aria-hidden="true" />;
}

function StepList({ active, reply }: { active: number; reply: PlanResult | null }) {
  return (
    <ol className="space-y-1" aria-live="polite" aria-label="What the agent is doing">
      {STEPS.map((step, i) => {
        const done = i < active;
        const current = i === active;
        const detail = reply?.steps.find((s) => s.id === step.id)?.detail;
        return (
          <li key={step.id} className={`flex gap-3 rounded-xl px-3 py-2.5 transition-colors ${current ? "bg-white shadow-[0_1px_0_#E2E0D8]" : ""}`}>
            <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center">
              {done ? (
                <span className="grid h-5 w-5 place-items-center rounded-full bg-[#556B2F] text-[11px] font-bold text-white" aria-hidden="true">✓</span>
              ) : current ? (
                <Spinner />
              ) : (
                <span className="h-2.5 w-2.5 rounded-full bg-[#E2E0D8]" aria-hidden="true" />
              )}
            </span>
            <span className="min-w-0">
              <span className={`block text-[13px] ${done ? "font-medium text-[#1C1C1C]" : current ? "font-semibold text-[#1C1C1C]" : "text-[#B5B3AA]"}`}>
                {step.title}
              </span>
              {(done || current) && (
                <span className="mt-0.5 block text-[11.5px] leading-snug text-[#8C8A82]">
                  {done && detail ? detail : current ? <span className="inline-block h-2 w-40 animate-pulse rounded bg-[#E2E0D8] align-middle" /> : ""}
                </span>
              )}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function Bar({ label, value, max, tone }: { label: string; value: number; max: number; tone: "plan" | "simple" }) {
  return (
    <div className="flex items-center gap-2 text-[11.5px]">
      <span className="w-[122px] shrink-0 text-[#8C8A82]">{label}</span>
      <span className="h-2 flex-1 overflow-hidden rounded bg-[#E2E0D8]" aria-hidden="true">
        <span className={`block h-full rounded ${tone === "plan" ? "bg-[#556B2F]" : "bg-[#B5B3AA]"}`} style={{ width: `${(value / max) * 100}%` }} />
      </span>
      <span className="w-6 text-right font-semibold text-[#1C1C1C]">{value}</span>
    </div>
  );
}

function Purchase({ purchase }: { purchase: PlanPurchase }) {
  const [shops, setShops] = useState(false);
  const shown = purchase.closes.slice(0, 4);
  return (
    <li className="rounded-2xl border border-[#E2E0D8] bg-white p-3.5">
      <div className="flex items-start gap-3">
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-[#556B2F] font-display text-[14px] text-white">{purchase.order}</span>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <h3 className="text-[14px] font-semibold text-[#1C1C1C]">{purchase.name}</h3>
            <span className="shrink-0 text-[12px] font-semibold text-[#1C1C1C]" title={`Estimated range ${purchase.price_tnd.low}–${purchase.price_tnd.high} TND`}>
              ~{purchase.price_tnd.estimate} TND
            </span>
          </div>
          <p className="mt-0.5 text-[11.5px] text-[#8C8A82]">
            Closes {purchase.closes.length} need{purchase.closes.length === 1 ? "" : "s"} · {purchase.price_tnd.low}–{purchase.price_tnd.high} TND
          </p>
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {shown.map((c) => (
              <li
                key={`${c.goal}:${c.candidate_id}`}
                title={`${c.goal_label}: ${c.need}${c.completes ? " (completed by this piece)" : " (one more piece needed after this one)"}`}
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] ${c.completes ? "bg-[#E8EDE0] text-[#415638]" : "bg-[#F4EEDD] text-[#8A7130]"}`}
              >
                <span aria-hidden="true">{GOAL_DESIGN[c.goal]?.icon ?? "◐"}</span>
                {GOAL_DESIGN[c.goal]?.short ?? c.goal_label} · {c.need}
              </li>
            ))}
            {purchase.closes.length > shown.length && <li className="px-1 py-0.5 text-[11px] text-[#8C8A82]">+{purchase.closes.length - shown.length} more</li>}
          </ul>
          {purchase.can_search_shops && (
            <button onClick={() => setShops((o) => !o)} aria-expanded={shops} className="mt-2 text-[11.5px] font-semibold text-[#556B2F] hover:underline">
              {shops ? "Hide shops" : "See Tunisian shops"}
            </button>
          )}
          {shops && <PlanPhotos category={purchase.category} subcategory={purchase.subcategory} />}
        </div>
      </div>
    </li>
  );
}

function Result({ plan, onReset }: { plan: PlanResult; onReset: () => void }) {
  const { totals, baseline } = plan;
  const max = Math.max(totals.needs_closed, baseline.needs_closed, 1);
  return (
    <div className="space-y-3">
      <section className="rounded-2xl border border-[#E2E0D8] bg-white p-4">
        <div className="flex items-center gap-2">
          <p className="text-[10px] font-bold uppercase tracking-[1.6px] text-[#556B2F]">Your plan</p>
          {plan.summary_source === "ai" && <span className="rounded-full bg-[#E8EDE0] px-2 py-0.5 text-[10px] font-semibold text-[#415638]">written by the language model</span>}
        </div>
        <p className="mt-1.5 text-[13px] leading-relaxed text-[#1C1C1C]">{plan.summary}</p>
        {plan.rationale && <p className="mt-1.5 text-[11.5px] italic text-[#8C8A82]">{plan.rationale}</p>}

        {plan.purchases.length > 0 && (
          <>
            <dl className="mt-3 grid grid-cols-3 gap-2 text-center">
              {[
                ["Pieces", String(totals.pieces)],
                ["Estimated", `${totals.estimated_cost} TND`],
                ["Needs closed", `${totals.needs_closed}/${totals.needs_open_before}`],
              ].map(([label, value]) => (
                <div key={label} className="rounded-xl bg-[#FAF9F6] px-2 py-2">
                  <dt className="text-[10px] uppercase tracking-wide text-[#8C8A82]">{label}</dt>
                  <dd className="font-display text-[17px] font-semibold text-[#1C1C1C]">{value}</dd>
                </div>
              ))}
            </dl>
            {plan.budget_tnd && (
              <div className="mt-3">
                <div className="flex justify-between text-[11px] text-[#8C8A82]">
                  <span>Budget used</span>
                  <span>{totals.estimated_cost} of {Math.round(plan.budget_tnd)} TND</span>
                </div>
                <div className="mt-1 h-2 overflow-hidden rounded bg-[#E2E0D8]" aria-hidden="true">
                  <div className="h-full rounded bg-[#556B2F]" style={{ width: `${Math.min(100, (totals.estimated_cost / plan.budget_tnd) * 100)}%` }} />
                </div>
              </div>
            )}
            <div className="mt-3 space-y-1.5" aria-label="Needs closed, planner against the simple method">
              <Bar label="This plan" value={totals.needs_closed} max={max} tone="plan" />
              <Bar label="One gap per context" value={baseline.needs_closed} max={max} tone="simple" />
            </div>
          </>
        )}
        {plan.note && <p className="mt-3 rounded-lg bg-[#FAF9F6] px-3 py-2 text-[12px] text-[#8A7130]">{plan.note}</p>}
      </section>

      {plan.purchases.length > 0 && (
        <ol className="space-y-2.5" aria-label="Pieces to buy, in order">
          {plan.purchases.map((p) => <Purchase key={`${p.category}:${p.subcategory}`} purchase={p} />)}
        </ol>
      )}

      <p className="px-1 text-[10.5px] leading-snug text-[#8C8A82]">
        {plan.price_note} The rules decide what is missing; the language model only reads your goal and phrases the result.
      </p>
      <button onClick={onReset} className="w-full rounded-xl border border-[#E2E0D8] bg-white py-2.5 text-[13px] font-semibold text-[#1C1C1C] hover:border-[#556B2F]">
        New plan
      </button>
    </div>
  );
}

// The agent: a goal and a budget in, a step-by-step run you can watch, an ordered shopping plan out.
export default function PlannerPanel() {
  const [objective, setObjective] = useState("");
  const [budget, setBudget] = useState("");
  const [phase, setPhase] = useState<"idle" | "running" | "done" | "error">("idle");
  const [active, setActive] = useState(0);
  const [reply, setReply] = useState<PlanResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = useRef(0); // ignores the answer of a run that was replaced

  const last = STEPS.length - 1;
  const stepMs = reducedMotion() ? 120 : 950;

  // The run advances one step at a time, however fast the server answers.
  useEffect(() => {
    if (phase !== "running") return;
    const timer = setInterval(() => setActive((a) => Math.min(a + 1, last)), stepMs);
    return () => clearInterval(timer);
  }, [phase, last, stepMs]);

  // The last step finishes only when the plan has arrived.
  useEffect(() => {
    if (phase !== "running" || !reply || active < last) return;
    const timer = setTimeout(() => {
      setActive(STEPS.length);
      setPhase("done");
    }, reducedMotion() ? 0 : 900);
    return () => clearTimeout(timer);
  }, [phase, reply, active, last]);

  const start = () => {
    const amount = budget.trim() === "" ? null : Number(budget);
    if (amount !== null && (!Number.isFinite(amount) || amount <= 0 || amount > 100000)) {
      setError("The budget must be a positive number of dinars.");
      setPhase("error");
      return;
    }
    const id = ++run.current;
    setPhase("running");
    setActive(0);
    setReply(null);
    setError(null);
    fetchPlan(objective.trim(), amount)
      .then((plan) => id === run.current && setReply(plan))
      .catch((e: Error) => {
        if (id !== run.current) return;
        setError(e.message);
        setPhase("error");
      });
  };

  const reset = () => {
    run.current++;
    setPhase("idle");
    setReply(null);
    setError(null);
  };

  const busy = phase === "running";
  return (
    <div className="flex-1 space-y-3 overflow-y-auto bg-[#FAF9F6] p-4">
      {(phase === "idle" || phase === "error" || busy) && (
        <section className="rounded-2xl border border-[#E2E0D8] bg-white p-4">
          <h2 className="font-display text-[18px] font-semibold text-[#1C1C1C]">What are you preparing for?</h2>
          <p className="mt-1 text-[12px] leading-relaxed text-[#8C8A82]">
            Tell me your goal and budget. I look at every context, find the few pieces that close the most needs, and order them.
          </p>
          <label htmlFor="plan-goal" className="sr-only">Your goal</label>
          <textarea
            id="plan-goal"
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            disabled={busy}
            maxLength={300}
            rows={3}
            placeholder="e.g. A wedding in August and a winter internship"
            className="mt-3 w-full resize-none rounded-xl border border-[#E2E0D8] bg-[#FAF9F6] px-3 py-2.5 text-[13px] outline-none focus:border-[#556B2F] disabled:opacity-60"
          />
          <div className="mt-2 flex flex-wrap gap-1.5">
            {EXAMPLES.map((example) => (
              <button
                key={example}
                type="button"
                disabled={busy}
                onClick={() => setObjective(example)}
                className="rounded-full border border-[#E2E0D8] bg-[#FAF9F6] px-2.5 py-1 text-[11px] text-[#1C1C1C] hover:border-[#556B2F] disabled:opacity-50"
              >
                {example}
              </button>
            ))}
          </div>
          <div className="mt-3 flex items-end gap-2">
            <div className="w-[140px]">
              <label htmlFor="plan-budget" className="block text-[11px] font-semibold text-[#8C8A82]">Budget (optional)</label>
              <div className="mt-1 flex items-center rounded-xl border border-[#E2E0D8] bg-[#FAF9F6] focus-within:border-[#556B2F]">
                <input
                  id="plan-budget"
                  type="number"
                  inputMode="numeric"
                  min={1}
                  value={budget}
                  onChange={(e) => setBudget(e.target.value)}
                  disabled={busy}
                  placeholder="300"
                  className="w-full bg-transparent px-3 py-2.5 text-[13px] outline-none disabled:opacity-60"
                />
                <span className="pr-3 text-[12px] text-[#8C8A82]">TND</span>
              </div>
            </div>
            <button
              onClick={start}
              disabled={busy}
              className="flex-1 rounded-xl bg-[#556B2F] py-2.5 text-[13px] font-semibold text-white hover:bg-[#6B8A3A] disabled:opacity-60"
            >
              {busy ? "Planning…" : "✦ Plan my purchases"}
            </button>
          </div>
          <p className="mt-2 text-[10.5px] text-[#8C8A82]">Leave the goal empty to plan for all contexts without using the language model.</p>
          {error && <p role="alert" className="mt-2 text-[12px] text-[#9A5A3C]">{error}</p>}
        </section>
      )}

      {busy && (
        <section className="rounded-2xl border border-[#E2E0D8] bg-[#FAF9F6] p-2">
          <StepList active={active} reply={reply} />
        </section>
      )}

      {phase === "done" && reply && (
        <>
          <details className="group rounded-2xl border border-[#E2E0D8] bg-white">
            <summary className="cursor-pointer list-none px-4 py-3 text-[12px] font-semibold text-[#556B2F]">
              ✓ The agent ran {STEPS.length} steps{reply.cached ? " (saved result)" : ""} · show what it did
            </summary>
            <div className="px-2 pb-2">
              <StepList active={STEPS.length} reply={reply} />
            </div>
          </details>
          <Result plan={reply} onReset={reset} />
        </>
      )}
    </div>
  );
}
