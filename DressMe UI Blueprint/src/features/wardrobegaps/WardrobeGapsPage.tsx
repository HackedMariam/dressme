import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  fetchGaps,
  fetchGoals,
  fetchLearning,
  resetRanker,
  retrainRanker,
  sendChat,
  sendFeedback,
  type ChatTurn,
  type CoveredRequirement,
  type GapRanking,
  type Goal,
  type LearningStatus,
  type RankedGap,
  type TraceStep,
  type TrainingRun,
} from "./api";

const GOAL_DESIGN: Record<string, { icon: string; note: string; prompt: string }> = {
  winter_work: { icon: "❄", note: "Office days, rain & cold", prompt: "What am I missing for winter work days in Tunis?" },
  summer_casual: { icon: "☀", note: "Light & breathable", prompt: "What am I missing for hot summer days?" },
  formal_event: { icon: "✦", note: "Weddings & celebrations", prompt: "What am I missing for a summer wedding?" },
};

const FEATURES: { key: keyof RankedGap; label: string; inverse?: boolean }[] = [
  { key: "coverage_deficit", label: "Coverage deficit" },
  { key: "use_frequency", label: "Use frequency" },
  { key: "season_relevance", label: "Season relevance" },
  { key: "outfit_gain", label: "Outfit gain" },
  { key: "preference_match", label: "Preference match" },
  { key: "redundancy_score", label: "Redundancy", inverse: true },
];

const priorityTag = {
  high: "bg-[#F5E6DC] text-[#9A5A3C]",
  medium: "bg-[#F4EEDD] text-[#8A7130]",
  low: "bg-[#E8EDE0] text-[#556B2F]",
};

const DISMISSED_KEY = "dressme.bo3.dismissed";
const CONFIRMED_KEY = "dressme.bo3.confirmed";

function readList(key: string): string[] {
  try {
    return JSON.parse(localStorage.getItem(key) ?? "[]");
  } catch {
    return [];
  }
}

function usePersistentList(key: string) {
  const [list, setList] = useState<string[]>(() => readList(key));
  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(list));
    } catch {
      // Feedback still works for this session without storage.
    }
  }, [key, list]);
  const toggle = (id: string, on: boolean) => setList((l) => (on ? [...new Set([...l, id])] : l.filter((x) => x !== id)));
  return [list, toggle] as const;
}

// Coverage = owned units / required units across every requirement of the goal.
function coverage(gaps: RankedGap[], covered: CoveredRequirement[], filled?: string) {
  const all = [...gaps, ...covered];
  const required = all.reduce((t, r) => t + r.required_count, 0);
  const owned = all.reduce(
    (t, r) => t + (r.candidate_id === filled ? r.required_count : Math.min(r.owned_count, r.required_count)),
    0,
  );
  return required ? Math.round((owned / required) * 100) : 0;
}

function reasonFor(gap: RankedGap) {
  const ownership =
    gap.owned_count === 0 ? "Nothing in your wardrobe covers this yet" : `You own ${gap.owned_count} of the ${gap.required_count} needed`;
  const strongest = FEATURES.filter((f) => !f.inverse && f.key !== "coverage_deficit")
    .sort((a, b) => (gap[b.key] as number) - (gap[a.key] as number))[0];
  return `${ownership}. Strongest signal: ${strongest.label.toLowerCase()} (${(gap[strongest.key] as number).toFixed(2)}).`;
}

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) =>
    part.startsWith("**") ? (
      <strong key={i}>{part.slice(2, -2)}</strong>
    ) : part.startsWith("`") ? (
      <code key={i} className="text-[12px] bg-[#F0EFEA] px-1 rounded">{part.slice(1, -1)}</code>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

function AgentMarkdown({ text }: { text: string }) {
  return (
    <div className="space-y-1.5">
      {text.split("\n").map((line, i) => {
        const trimmed = line.trim();
        if (!trimmed) return null;
        const bullet = trimmed.match(/^[-*]\s+(.*)/);
        return bullet ? <p key={i} className="pl-4">• {inline(bullet[1])}</p> : <p key={i}>{inline(trimmed)}</p>;
      })}
    </div>
  );
}

function CoverageRing({ score }: { score: number | null }) {
  return (
    <div
      className="w-[82px] h-[82px] rounded-full grid place-items-center shrink-0"
      style={{ background: `conic-gradient(#556B2F ${(score ?? 0) * 3.6}deg, #E2E0D8 0)` }}
      role="img"
      aria-label={`Wardrobe coverage: ${score === null ? "loading" : `${score}%`}`}
    >
      <span className="bg-white w-[66px] h-[66px] rounded-full grid place-items-center text-xl font-bold text-[#1C1C1C]">
        {score === null ? "—" : `${score}%`}
      </span>
    </div>
  );
}

function TraceView({ trace }: { trace: TraceStep[] }) {
  const [open, setOpen] = useState(false);
  if (trace.length === 0) return null;
  return (
    <div className="mt-2">
      <button onClick={() => setOpen(!open)} className="text-[11px] text-[#556B2F] font-semibold hover:underline">
        {open ? "Hide" : "Show"} agent pipeline · {trace.length} tool call{trace.length > 1 ? "s" : ""}
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {trace.map((entry, i) => (
            <div key={i} className="bg-[#1C1C1C] rounded-lg p-3 text-[11px]">
              <p className="text-white/80 font-mono">
                <span className="text-[#8FA866]">step {entry.step}</span> · {entry.tool}({JSON.stringify(entry.arguments)})
              </p>
              <pre className="text-white/50 mt-1.5 max-h-40 overflow-auto whitespace-pre-wrap">{JSON.stringify(entry.result, null, 2)}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Exact TreeSHAP values: base value + contributions = ranking score.
function ShapPanel({ gap }: { gap: RankedGap }) {
  const rows = FEATURES.map((f) => ({ ...f, value: gap[f.key] as number, contribution: gap.shap.contributions[f.key] ?? 0 })).sort(
    (a, b) => Math.abs(b.contribution) - Math.abs(a.contribution),
  );
  const scale = Math.max(...rows.map((r) => Math.abs(r.contribution)), 0.01);
  return (
    <div className="bg-[#FAF9F6] rounded-lg p-4 mb-3">
      <p className="text-[10.5px] font-bold tracking-widest uppercase text-[#8C8A82]">Why this piece · SHAP explanation</p>
      <p className="text-[11px] text-[#8C8A82] mt-1 mb-3">How much each feature pushed this piece up or down the ranking.</p>
      <div className="space-y-2">
        {rows.map((r) => {
          const width = (Math.abs(r.contribution) / scale) * 50;
          const up = r.contribution >= 0;
          return (
            <div key={r.key} className="grid grid-cols-[118px_1fr_48px] items-center gap-2 text-[11px]">
              <span className="text-[#1C1C1C] truncate" title={`${r.label}: feature value ${r.value.toFixed(2)}`}>
                {r.label} <span className="text-[#8C8A82]">{r.value.toFixed(2)}</span>
              </span>
              <div className="relative h-2.5 bg-[#EFEBE4] rounded">
                <div className="absolute left-1/2 top-[-2px] bottom-[-2px] w-px bg-[#C9C2B6]" />
                <div
                  className={`absolute top-0 bottom-0 rounded ${up ? "bg-[#556B2F]" : "bg-[#B9714F]"}`}
                  style={up ? { left: "50%", width: `${width}%` } : { right: "50%", width: `${width}%` }}
                />
              </div>
              <span className={`text-right font-mono ${up ? "text-[#556B2F]" : "text-[#9A5A3C]"}`}>
                {up ? "+" : ""}{r.contribution.toFixed(2)}
              </span>
            </div>
          );
        })}
      </div>
      <p className="text-[11px] text-[#8C8A82] pt-3">
        Base {gap.shap.base_value.toFixed(2)} + contributions = ranking score <b className="text-[#1C1C1C]">{gap.ranking_score.toFixed(2)}</b>.
        Scores order pieces; they are not probabilities.
      </p>
    </div>
  );
}

function GapCard({
  gap,
  rank,
  currentCoverage,
  coverageAfter,
  confirmed,
  onConfirm,
  onDismiss,
  onAsk,
}: {
  gap: RankedGap;
  rank: number;
  currentCoverage: number;
  coverageAfter: number;
  confirmed: boolean;
  onConfirm: () => void;
  onDismiss: () => void;
  onAsk: () => void;
}) {
  const [preview, setPreview] = useState(false);
  const [why, setWhy] = useState(false);
  return (
    <article className="bg-white border border-[#E2E0D8] rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="font-display text-[17px] text-[#8C8A82] mr-auto">{String(rank).padStart(2, "0")}</span>
        <span className={`text-[11px] font-bold px-2 py-0.5 rounded-md capitalize ${priorityTag[gap.priority]}`}>{gap.priority}</span>
        {confirmed && <span className="text-[11px] font-bold px-2 py-0.5 rounded-md bg-[#1C1C1C] text-white">I need this</span>}
      </div>

      <div className="flex gap-3 items-center">
        <div className="w-[64px] h-[64px] rounded-xl bg-[#F0EFEA] grid place-items-center text-[26px] text-[#556B2F] shrink-0">◐</div>
        <div className="min-w-0">
          <h3 className="font-display text-[19px] font-medium text-[#1C1C1C] leading-snug">{gap.name}</h3>
          <p className="text-xs text-[#8C8A82] mt-0.5">Suggested: {gap.suggested_item}</p>
        </div>
      </div>

      <p className="text-xs text-[#8C8A82] py-2.5">{reasonFor(gap)}</p>

      <div className="flex items-center gap-2.5 px-3 py-2.5 rounded-lg bg-[#E8EDE0] text-[#415638]">
        <span className="text-lg">✦</span>
        <div>
          <strong className="text-[19px]">+{gap.pairable_owned_items}</strong>
          <span className="text-[11px]"> owned pieces it combines with this season</span>
        </div>
      </div>

      <button
        onClick={() => setPreview(!preview)}
        aria-expanded={preview}
        className="w-full flex items-center justify-between py-2.5 text-xs font-bold text-[#556B2F]"
      >
        {preview ? "Hide coverage preview" : "Your wardrobe with this piece"} <span>→</span>
      </button>
      {preview && (
        <div className="bg-[#FAF9F6] rounded-lg p-4 mb-3">
          <p className="text-[10.5px] font-bold tracking-widest uppercase text-[#8C8A82]">Estimated coverage with this piece</p>
          <div className="flex items-center gap-4 text-2xl py-3">
            <span>{currentCoverage}% <small className="block text-[10px] text-[#8C8A82]">now</small></span>
            <span className="text-[#8C8A82]">→</span>
            <strong className="text-[#556B2F]">{coverageAfter}% <small className="block text-[10px] text-[#8C8A82] font-normal">with this piece</small></strong>
          </div>
          <p className="text-xs text-[#8C8A82]">
            {gap.matched_items.length ? `Already counted: ${gap.matched_items.join(", ")}.` : "No owned piece fulfils this need yet."}
            {gap.redundancy_score >= 0.6 && ` Check your ${gap.closest_owned_item} first — it is similar.`}
          </p>
        </div>
      )}

      {why && <ShapPanel gap={gap} />}

      <div className="flex flex-wrap gap-1.5 border-t border-[#E2E0D8] pt-2.5">
        {[
          { label: why ? "Hide why" : "Why this piece?", onClick: () => setWhy(!why), pressed: why },
          { label: confirmed ? "✓ I need this" : "I need this", onClick: onConfirm, pressed: confirmed },
          { label: "Not relevant", onClick: onDismiss, pressed: false },
        ].map((b) => (
          <button
            key={b.label}
            onClick={b.onClick}
            aria-pressed={b.pressed}
            className="px-2.5 py-1.5 text-xs font-bold rounded-lg border border-[#D6D0C5] bg-white text-[#1C1C1C] hover:bg-[#FAF9F6]"
          >
            {b.label}
          </button>
        ))}
      </div>
      <button onClick={onAsk} className="w-full mt-2.5 py-2.5 rounded-lg bg-[#1C1C1C] hover:bg-black text-white text-[13px] font-bold">
        Ask the agent about this piece →
      </button>
    </article>
  );
}

type Movement = { id: string; name: string; before: number; after: number };

function LearningLoop({
  status,
  training,
  movements,
  busy,
  error,
  onRetrain,
  onReset,
}: {
  status: LearningStatus | null;
  training: TrainingRun | null;
  movements: Movement[];
  busy: boolean;
  error: string | null;
  onRetrain: () => void;
  onReset: () => void;
}) {
  const run = training ?? status?.last_training ?? null;
  return (
    <section className="bg-white border border-[#E2E0D8] rounded-2xl p-6" aria-label="Learning loop">
      <div className="flex items-start justify-between gap-4">
        <div>
          <span className="text-[10.5px] font-bold tracking-[1.5px] uppercase text-[#8C8A82]">03 · Learning loop</span>
          <h2 className="font-display text-[23px] text-[#1C1C1C] mt-1">The ranker learns from you</h2>
          <p className="text-xs text-[#8C8A82] mt-1 max-w-[640px]">
            Every “I need this” and “Not relevant” becomes a training label. Retraining blends your labels with the synthetic data,
            weighting yours higher, and the new XGBoost model replaces the old one immediately.
          </p>
        </div>
        <span
          className={`shrink-0 text-[11px] font-bold px-2.5 py-1 rounded-md ${
            status?.personalised ? "bg-[#556B2F] text-white" : "bg-[#EDEAF2] text-[#5E5675]"
          }`}
        >
          {status?.personalised ? "Personalised model" : "Synthetic model"}
        </span>
      </div>

      <div className="grid grid-cols-4 gap-3 mt-5">
        {[
          { label: "Your labels", value: status?.feedback_labels ?? "—", note: `${status?.need_labels ?? 0} need · ${status?.not_relevant_labels ?? 0} not relevant` },
          { label: "Model in use", value: status?.personalised ? "v-you" : "v-synthetic", note: status?.active_model ?? "" },
          { label: "NDCG@3 before", value: run?.ndcg_at_3_before?.toFixed(2) ?? "—", note: "on your feedback" },
          { label: "NDCG@3 after", value: run?.ndcg_at_3_after?.toFixed(2) ?? "—", note: run ? run.evaluation : "retrain to measure" },
        ].map((s) => (
          <div key={s.label} className="bg-[#FAF9F6] rounded-xl p-4">
            <span className="text-[10.5px] font-bold tracking-[1.5px] uppercase text-[#8C8A82]">{s.label}</span>
            <strong className="block font-display text-2xl mt-1.5 text-[#1C1C1C]">{s.value}</strong>
            <p className="text-[10.5px] text-[#8C8A82] mt-0.5 truncate" title={s.note}>{s.note}</p>
          </div>
        ))}
      </div>

      {movements.length > 0 && (
        <div className="mt-5">
          <p className="text-[10.5px] font-bold tracking-[1.5px] uppercase text-[#8C8A82] mb-2">How the ranking changed for this context</p>
          <div className="grid grid-cols-2 gap-x-6">
            {movements.map((m) => {
              const delta = m.before - m.after;
              return (
                <div key={m.id} className="flex items-center gap-3 py-2 border-b border-[#E2E0D8] text-xs">
                  <span className="text-[#8C8A82] w-12 font-mono">#{m.before} → #{m.after}</span>
                  <span className="flex-1 text-[#1C1C1C]">{m.name}</span>
                  <span className={`font-bold ${delta > 0 ? "text-[#556B2F]" : delta < 0 ? "text-[#9A5A3C]" : "text-[#8C8A82]"}`}>
                    {delta > 0 ? `▲ ${delta}` : delta < 0 ? `▼ ${-delta}` : "="}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {error && <p className="text-xs text-[#9A5A3C] mt-4">{error}</p>}
      <div className="flex flex-wrap items-center gap-2 mt-5">
        <button
          onClick={onRetrain}
          disabled={busy || !status?.feedback_labels}
          className="bg-[#1C1C1C] hover:bg-black disabled:opacity-40 text-white text-[13px] font-bold px-4 py-2.5 rounded-lg"
        >
          {busy ? "Retraining…" : "Retrain from my feedback"}
        </button>
        {status?.personalised && (
          <button
            onClick={onReset}
            disabled={busy}
            className="px-4 py-2.5 text-[13px] font-bold rounded-lg border border-[#D6D0C5] bg-white hover:bg-[#FAF9F6]"
          >
            Reset to synthetic model
          </button>
        )}
        <span className="text-[11px] text-[#8C8A82]">
          {status?.feedback_labels ? "Unrated pieces in a rated context count as neutral." : "Rate at least one piece above to enable retraining."}
        </span>
      </div>
    </section>
  );
}

type Message = ChatTurn & { trace?: TraceStep[] };

function AgentDrawer({
  open,
  onClose,
  messages,
  thinking,
  error,
  onSend,
  suggestion,
}: {
  open: boolean;
  onClose: () => void;
  messages: Message[];
  thinking: boolean;
  error: string | null;
  onSend: (text: string) => void;
  suggestion: string;
}) {
  const [input, setInput] = useState("");
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages, thinking]);
  if (!open) return null;
  const send = (text: string) => {
    onSend(text);
    setInput("");
  };
  return (
    <div className="fixed top-0 right-0 bottom-0 w-[460px] max-w-full bg-white border-l border-[#E2E0D8] shadow-[-20px_0_40px_rgba(40,30,20,.12)] z-[60] flex flex-col">
      <div className="px-5 py-4 border-b border-[#E2E0D8] flex items-start gap-3">
        <div className="flex-1">
          <p className="text-[11px] font-bold tracking-[1.8px] uppercase text-[#556B2F]">BO3 · Gap Agent</p>
          <p className="text-[11px] text-[#8C8A82] mt-0.5">GPT-4o mini · tools: coverage rules, FashionCLIP, XGBoost, memory</p>
        </div>
        <button onClick={onClose} aria-label="Close agent" className="text-[#8C8A82] hover:text-[#1C1C1C] text-lg">×</button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-[#FAF9F6]">
        {messages.length === 0 && (
          <button
            onClick={() => send(suggestion)}
            className="block w-full text-left text-xs bg-white border border-[#E2E0D8] px-3 py-2 rounded-lg hover:border-[#556B2F]"
          >
            {suggestion}
          </button>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
            <div
              className={`rounded-2xl px-4 py-3 text-[13px] leading-relaxed ${
                m.role === "user" ? "bg-[#1C1C1C] text-white rounded-tr-none max-w-[85%]" : "bg-white border border-[#E2E0D8] text-[#1C1C1C] rounded-tl-none"
              }`}
            >
              {m.role === "assistant" ? <AgentMarkdown text={m.content} /> : m.content}
              {m.trace && <TraceView trace={m.trace} />}
            </div>
          </div>
        ))}
        {thinking && <p className="text-xs text-[#8C8A82]">Agent is calling tools…</p>}
        {error && <p className="text-xs text-[#9A5A3C]">Error: {error}</p>}
        <div ref={end} />
      </div>

      <div className="p-3 border-t border-[#E2E0D8] flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send(input)}
          placeholder="Ask about your wardrobe gaps…"
          className="flex-1 px-3 py-2.5 bg-white border border-[#E2E0D8] rounded-xl text-sm outline-none focus:border-[#556B2F]"
        />
        <button
          onClick={() => send(input)}
          disabled={thinking}
          className="bg-[#556B2F] hover:bg-[#6B8A3A] disabled:opacity-50 text-white px-4 rounded-xl text-sm font-semibold"
        >
          Send
        </button>
      </div>
    </div>
  );
}

export default function WardrobeGapsPage() {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [goal, setGoal] = useState("winter_work");
  const [ranking, setRanking] = useState<GapRanking | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dismissed, toggleDismissed] = usePersistentList(DISMISSED_KEY);
  const [confirmed, toggleConfirmed] = usePersistentList(CONFIRMED_KEY);
  const piecesRef = useRef<HTMLElement>(null);

  const [learning, setLearning] = useState<LearningStatus | null>(null);
  const [training, setTraining] = useState<TrainingRun | null>(null);
  const [movements, setMovements] = useState<Movement[]>([]);
  const [learningBusy, setLearningBusy] = useState(false);
  const [learningError, setLearningError] = useState<string | null>(null);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [thinking, setThinking] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);

  useEffect(() => {
    fetchGoals().then(setGoals).catch((e: Error) => setError(e.message));
    fetchLearning().then(setLearning).catch(() => undefined);
  }, []);

  useEffect(() => {
    setRanking(null);
    setError(null);
    setMovements([]);
    fetchGaps(goal).then(setRanking).catch((e: Error) => setError(e.message));
  }, [goal]);

  // Sends a label to the backend; the local list keeps the buttons in sync across reloads.
  const giveFeedback = (gap: RankedGap, relevance: 0 | 3 | null) => {
    setLearningError(null);
    sendFeedback(goal, gap.candidate_id, relevance)
      .then(setLearning)
      .catch((e: Error) => setLearningError(`Feedback not saved: ${e.message}`));
  };

  const runLearning = async (action: "retrain" | "reset") => {
    if (!ranking) return;
    setLearningBusy(true);
    setLearningError(null);
    const before = new Map(ranking.ranked_gaps.map((g) => [g.candidate_id, g.rank]));
    try {
      if (action === "retrain") {
        const result = await retrainRanker();
        setTraining(result.training);
        setLearning(result.status);
      } else {
        setTraining(null);
        setLearning(await resetRanker());
      }
      const next = await fetchGaps(goal);
      setRanking(next);
      setMovements(
        next.ranked_gaps.map((g) => ({ id: g.candidate_id, name: g.name, before: before.get(g.candidate_id) ?? g.rank, after: g.rank })),
      );
    } catch (e) {
      setLearningError((e as Error).message);
    } finally {
      setLearningBusy(false);
    }
  };

  const key = (id: string) => `${goal}:${id}`;
  const visible = useMemo(() => ranking?.ranked_gaps.filter((g) => !dismissed.includes(key(g.candidate_id))) ?? [], [ranking, dismissed, goal]);
  const score = ranking ? coverage(ranking.ranked_gaps, ranking.covered) : null;
  const totalRequirements = ranking ? ranking.ranked_gaps.length + ranking.covered.length : 0;
  const goalLabel = goals.find((g) => g.id === goal)?.label ?? "";
  const dismissedHere = ranking?.ranked_gaps.filter((g) => dismissed.includes(key(g.candidate_id))) ?? [];

  const ask = async (text: string) => {
    const message = text.trim();
    if (!message || thinking) return;
    setDrawerOpen(true);
    const history: ChatTurn[] = messages.map(({ role, content }) => ({ role, content }));
    setMessages((m) => [...m, { role: "user", content: message }]);
    setThinking(true);
    setChatError(null);
    try {
      const response = await sendChat(message, history, conversationId);
      setConversationId(response.conversation_id);
      setMessages((m) => [...m, { role: "assistant", content: response.answer, trace: response.trace }]);
      if (response.ranking && response.ranking.goal !== goal) setGoal(response.ranking.goal);
    } catch (e) {
      setChatError((e as Error).message);
    } finally {
      setThinking(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-bold tracking-[1.8px] uppercase text-[#556B2F]">BO3 · Wardrobe Gaps</p>
          <h1 className="font-display text-3xl font-semibold text-[#1C1C1C] mt-1">A wardrobe ready for your life.</h1>
          <p className="text-[#8C8A82] text-sm mt-1">Discover what you already cover, what needs attention, and the pieces that make a difference.</p>
        </div>
        <button
          onClick={() => setDrawerOpen(true)}
          className="shrink-0 inline-flex items-center gap-2 bg-[#556B2F] hover:bg-[#6B8A3A] text-white text-sm font-semibold px-4 py-2.5 rounded-lg"
        >
          ✦ Ask the Gap Agent
        </button>
      </div>

      {/* Summary */}
      <section className="grid grid-cols-[1.35fr_1fr_1fr_1fr] gap-3.5" aria-label="Coverage summary">
        <div className="flex gap-4 items-center p-5 rounded-xl bg-[#E8EDE0] border border-[#CAD5C3]">
          <CoverageRing score={score} />
          <div>
            <h3 className="text-sm font-semibold text-[#1C1C1C]">Wardrobe coverage</h3>
            <p className="text-[11px] text-[#8C8A82] mt-1">{goalLabel}</p>
            <small className="text-[10px] text-[#8C8A82]">Owned pieces vs. pieces this context needs</small>
          </div>
        </div>
        <div className="p-5 rounded-xl bg-white border border-[#E2E0D8] flex flex-col justify-center">
          <span className="text-[10.5px] font-bold tracking-[1.5px] uppercase text-[#8C8A82]">Covered needs</span>
          <strong className="font-display text-3xl mt-2">{ranking ? `${ranking.covered.length} / ${totalRequirements}` : "—"}</strong>
          <p className="text-[11px] text-[#8C8A82] mt-1">Requirements fully met by pieces you own.</p>
        </div>
        <div className="p-5 rounded-xl bg-white border border-[#E2E0D8] flex flex-col justify-center">
          <span className="text-[10.5px] font-bold tracking-[1.5px] uppercase text-[#8C8A82]">Wardrobe pieces counted</span>
          <strong className="font-display text-3xl mt-2">
            {ranking ? new Set([...ranking.ranked_gaps, ...ranking.covered].flatMap((r) => r.matched_items)).size : "—"}
          </strong>
          <p className="text-[11px] text-[#8C8A82] mt-1">Owned items that satisfy at least one need.</p>
        </div>
        <div className="p-5 rounded-xl bg-[#1C1C1C] text-white flex flex-col justify-center">
          <span className="text-[10.5px] font-bold tracking-[1.5px] uppercase text-[#C6D2BF]">Missing pieces</span>
          <strong className="font-display text-3xl mt-2">{ranking ? visible.length : "—"}</strong>
          <p className="text-[12px] text-[#E1DDD5] mt-1">
            {ranking ? `${visible.filter((g) => g.priority === "high").length} high priority` : "Analysing…"}
          </p>
          {visible.length > 0 && (
            <button
              onClick={() => piecesRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
              className="self-start mt-1 text-xs font-bold underline underline-offset-4 text-[#E4EDDD] hover:text-white"
            >
              View missing pieces →
            </button>
          )}
        </div>
      </section>

      <details className="text-xs text-[#8C8A82] -mt-2">
        <summary className="cursor-pointer underline">How are these stats calculated?</summary>
        <p className="max-w-[900px] mt-2">
          Coverage rules decide whether a gap exists: each context lists the pieces it needs and how many. Coverage is the share of needed
          pieces you already own. Missing pieces are ordered by an XGBoost learning-to-rank model using six features — coverage deficit, use
          frequency, season relevance, outfit gain, preference match and FashionCLIP redundancy. The ranker is trained on synthetic data until
          real feedback is collected.
        </p>
      </details>

      {/* Context */}
      <section className="bg-white border border-[#E2E0D8] rounded-2xl p-6" aria-label="Context">
        <span className="text-[10.5px] font-bold tracking-[1.5px] uppercase text-[#8C8A82]">01 · Your context</span>
        <h2 className="font-display text-[23px] text-[#1C1C1C] mt-1 mb-4">What are you dressing for?</h2>
        <div className="grid grid-cols-3 gap-3">
          {goals.map((g) => {
            const on = g.id === goal;
            const design = GOAL_DESIGN[g.id] ?? { icon: "◐", note: g.season, prompt: "" };
            return (
              <button
                key={g.id}
                aria-pressed={on}
                onClick={() => setGoal(g.id)}
                className={`flex items-center gap-3 text-left px-4 py-4 rounded-xl border transition-all ${
                  on ? "bg-[#E8EDE0] border-[#556B2F] shadow-[inset_0_0_0_1px_#556B2F]" : "bg-[#FAF9F6] border-[#E2E0D8] hover:border-[#556B2F]"
                }`}
              >
                <span className={`w-10 h-10 rounded-xl grid place-items-center text-xl ${on ? "bg-[#DCE6D3] text-[#4C6441]" : "bg-white text-[#7B776F]"}`}>
                  {design.icon}
                </span>
                <span className="flex-1">
                  <b className="block text-sm text-[#1C1C1C]">{g.label}</b>
                  <small className="block text-[11px] text-[#8C8A82] mt-0.5">{design.note} · {g.season}</small>
                </span>
                <span
                  className={`w-[18px] h-[18px] rounded-full border grid place-items-center text-[10px] ${
                    on ? "bg-[#556B2F] border-[#556B2F] text-white" : "border-[#C6CBBF]"
                  }`}
                >
                  {on && "✓"}
                </span>
              </button>
            );
          })}
        </div>
      </section>

      {/* Missing pieces */}
      <section ref={piecesRef} className="scroll-mt-5" aria-label="Missing pieces">
        <div className="flex items-center justify-between gap-4 mb-4">
          <div>
            <span className="text-[10.5px] font-bold tracking-[1.5px] uppercase text-[#8C8A82]">02 · Missing pieces</span>
            <h2 className="font-display text-[23px] text-[#1C1C1C] mt-1">Missing pieces for your wardrobe</h2>
            <p className="text-xs text-[#8C8A82] mt-1">Ranked for {goalLabel.toLowerCase() || "this context"} by the BO3 ranker.</p>
          </div>
          <span className="inline-flex items-center gap-1.5 border border-[#E2E0D8] bg-[#E8EDE0] rounded-full px-3 py-2 text-[11px] whitespace-nowrap">
            ✦ {visible.length} suggestions
          </span>
        </div>

        {error && <div className="bg-white border border-[#E2E0D8] rounded-xl p-8 text-center text-sm text-[#8C8A82]">Gap agent unavailable: {error}</div>}
        {!ranking && !error && <div className="bg-white border border-[#E2E0D8] rounded-xl p-8 text-center text-sm text-[#8C8A82]">Analysing your wardrobe…</div>}

        <div className="grid grid-cols-2 gap-3.5 items-start">
          {ranking &&
            visible.map((gap, index) => (
              <GapCard
                key={gap.candidate_id}
                gap={gap}
                rank={index + 1}
                currentCoverage={score ?? 0}
                coverageAfter={coverage(ranking.ranked_gaps, ranking.covered, gap.candidate_id)}
                confirmed={confirmed.includes(key(gap.candidate_id))}
                onConfirm={() => {
                  const on = !confirmed.includes(key(gap.candidate_id));
                  toggleConfirmed(key(gap.candidate_id), on);
                  giveFeedback(gap, on ? 3 : null);
                }}
                onDismiss={() => {
                  toggleDismissed(key(gap.candidate_id), true);
                  toggleConfirmed(key(gap.candidate_id), false);
                  giveFeedback(gap, 0);
                }}
                onAsk={() => ask(`Tell me more about the "${gap.name}" gap for ${goalLabel.toLowerCase()}. Why is it ranked #${index + 1}?`)}
              />
            ))}
        </div>
        {ranking && visible.length === 0 && (
          <div className="bg-white border border-[#E2E0D8] rounded-xl p-9 text-center text-[#8C8A82]">
            <p className="text-2xl text-[#556B2F]">✓</p>
            <h3 className="text-sm font-semibold text-[#1C1C1C] mt-2">No missing pieces for this context</h3>
            <p className="text-xs mt-1">Try another context, or restore dismissed suggestions below.</p>
          </div>
        )}
      </section>

      <LearningLoop
        status={learning}
        training={training}
        movements={movements}
        busy={learningBusy}
        error={learningError}
        onRetrain={() => runLearning("retrain")}
        onReset={() => runLearning("reset")}
      />

      {/* Covered + feedback */}
      <div className="grid grid-cols-2 gap-4">
        <details className="bg-white border border-[#E2E0D8] rounded-2xl p-4">
          <summary className="cursor-pointer text-xs">
            <b>Already in your wardrobe</b> <span className="text-[#8C8A82]">· {ranking?.covered.length ?? 0} covered needs</span>
          </summary>
          {ranking?.covered.map((c) => (
            <div key={c.candidate_id} className="flex items-center gap-2.5 py-2.5 text-[#556B2F]">
              <span>✓</span>
              <span className="text-xs">
                <b className="text-[#1C1C1C]">{c.name}</b>
                <small className="block text-[#8C8A82]">Covered by {c.matched_items.join(", ")}</small>
              </span>
            </div>
          ))}
          {ranking && ranking.covered.length === 0 && <p className="text-xs text-[#8C8A82] mt-2">No need is fully covered yet for this context.</p>}
        </details>
        <details className="bg-white border border-[#E2E0D8] rounded-2xl p-4">
          <summary className="cursor-pointer text-xs">
            <b>Your feedback</b> <span className="text-[#8C8A82]">· {dismissedHere.length} dismissed</span>
          </summary>
          <p className="text-xs text-[#8C8A82] mt-2">Feedback is kept on this device. Restore a suggestion to include it again.</p>
          {dismissedHere.map((g) => (
            <div key={g.candidate_id} className="flex justify-between items-center gap-2 py-2">
              <span className="text-xs">{g.name}</span>
              <button
                onClick={() => {
                  toggleDismissed(key(g.candidate_id), false);
                  giveFeedback(g, null);
                }}
                className="px-2.5 py-1.5 text-xs font-bold rounded-lg border border-[#D6D0C5] bg-white hover:bg-[#FAF9F6]"
              >
                Restore
              </button>
            </div>
          ))}
          {dismissedHere.length === 0 && <p className="text-xs text-[#8C8A82] mt-2">No dismissed suggestions yet.</p>}
        </details>
      </div>

      <AgentDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        messages={messages}
        thinking={thinking}
        error={chatError}
        onSend={ask}
        suggestion={GOAL_DESIGN[goal]?.prompt ?? "What am I missing?"}
      />
    </div>
  );
}
