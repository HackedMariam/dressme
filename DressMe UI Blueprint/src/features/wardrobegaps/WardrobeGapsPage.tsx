import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchGaps,
  fetchGoals,
  sendChat,
  sendFeedback,
  type ChatTurn,
  type GapRanking,
  type Goal,
  type RankedGap,
  type WebPhoto,
} from "./api";
import AgentDrawer, { type Message } from "./AgentDrawer";
import ContextBar from "./ContextBar";
import GapDetail from "./GapDetail";
import GapList from "./GapList";
import SourceBanner from "./SourceBanner";
import { GOAL_DESIGN, coverage, feedbackKey, useConfirmedList, useDismissedList } from "./gapUtils";

// Two panes instead of a long scroll: the ranked list on the left, the selected piece on the right.
// On wide screens the page fits the window; the list and the detail scroll on their own if needed.
export default function WardrobeGapsPage() {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [goal, setGoal] = useState("winter_work");
  const [ranking, setRanking] = useState<GapRanking | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0); // bumped after a model refresh to rank again
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [photoThumbs, setPhotoThumbs] = useState<Record<string, string>>({}); // "goal:piece" -> first photo
  const [dismissed, toggleDismissed] = useDismissedList();
  const [confirmed, toggleConfirmed] = useConfirmedList();
  const [feedbackError, setFeedbackError] = useState<string | null>(null);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [thinking, setThinking] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);

  useEffect(() => {
    fetchGoals().then(setGoals).catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    setRanking(null);
    setError(null);
    fetchGaps(goal).then(setRanking).catch((e: Error) => setError(e.message));
  }, [goal, reload]);

  const isDismissed = useCallback((id: string) => dismissed.includes(feedbackKey(goal, id)), [dismissed, goal]);
  const isConfirmed = useCallback((id: string) => confirmed.includes(feedbackKey(goal, id)), [confirmed, goal]);

  // Select the first piece still to consider when a ranking arrives, so the right pane is never empty.
  useEffect(() => {
    if (!ranking) return;
    setSelectedId((current) => {
      if (current && ranking.ranked_gaps.some((g) => g.candidate_id === current)) return current;
      const first = ranking.ranked_gaps.find((g) => !isDismissed(g.candidate_id)) ?? ranking.ranked_gaps[0];
      return first?.candidate_id ?? null;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only a new ranking changes the default selection
  }, [ranking]);

  const changeGoal = (id: string) => {
    setSelectedId(null);
    setGoal(id);
  };

  // Arrow keys move through the list (not while typing, and not while the agent drawer is open).
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (drawerOpen || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
      const target = event.target as HTMLElement | null;
      if (target && (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable)) return;
      const gaps = ranking?.ranked_gaps ?? [];
      if (gaps.length === 0) return;
      event.preventDefault();
      const index = gaps.findIndex((g) => g.candidate_id === selectedId);
      const next = event.key === "ArrowDown" ? Math.min(gaps.length - 1, index + 1) : Math.max(0, index - 1);
      setSelectedId(gaps[next].candidate_id);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [ranking, selectedId, drawerOpen]);

  // Sends a label to the backend; the local list keeps the buttons in sync across reloads.
  const giveFeedback = (gap: RankedGap, relevance: 0 | 3 | null) => {
    setFeedbackError(null);
    sendFeedback(goal, gap.candidate_id, relevance).catch((e: Error) => setFeedbackError(`Feedback not saved: ${e.message}`));
  };
  const confirm = (gap: RankedGap) => {
    const key = feedbackKey(goal, gap.candidate_id);
    const on = !confirmed.includes(key);
    toggleConfirmed(key, on);
    if (on) toggleDismissed(key, false); // "I need this" replaces an earlier "Not relevant"
    giveFeedback(gap, on ? 3 : null);
  };
  const dismiss = (gap: RankedGap) => {
    const key = feedbackKey(goal, gap.candidate_id);
    toggleDismissed(key, true);
    toggleConfirmed(key, false);
    giveFeedback(gap, 0);
  };
  const restore = (gap: RankedGap) => {
    toggleDismissed(feedbackKey(goal, gap.candidate_id), false);
    giveFeedback(gap, null);
  };

  const rememberPhoto = (gap: RankedGap, photos: WebPhoto[]) => {
    if (photos[0]) setPhotoThumbs((t) => ({ ...t, [feedbackKey(goal, gap.candidate_id)]: photos[0].thumbnail }));
  };
  const thumbs = useMemo(() => {
    const here: Record<string, string> = {};
    for (const gap of ranking?.ranked_gaps ?? []) {
      const url = photoThumbs[feedbackKey(goal, gap.candidate_id)];
      if (url) here[gap.candidate_id] = url;
    }
    return here;
  }, [ranking, photoThumbs, goal]);

  const goalLabel = goals.find((g) => g.id === goal)?.label ?? "";
  const score = ranking ? coverage(ranking.ranked_gaps, ranking.covered) : null;
  const selected = ranking?.ranked_gaps.find((g) => g.candidate_id === selectedId) ?? null;
  const selectedIndex = selected && ranking ? ranking.ranked_gaps.indexOf(selected) : -1;
  const nothingToAnalyse = ranking?.wardrobe_source?.source === "empty" || ranking?.wardrobe_source?.source === "error";

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
      setMessages((m) => [...m, { role: "assistant", content: response.answer, trace: response.trace, items: response.items }]);
      if (response.ranking && response.ranking.goal !== goal) changeGoal(response.ranking.goal);
    } catch (e) {
      setChatError((e as Error).message);
    } finally {
      setThinking(false);
    }
  };

  return (
    <div className="flex flex-col gap-3 lg:h-[calc(100vh-5rem)] lg:min-h-[600px]">
      <ContextBar
        goals={goals}
        goal={goal}
        onGoal={changeGoal}
        score={score}
        department={ranking?.department}
        onAsk={() => setDrawerOpen(true)}
        onRankingChanged={() => setReload((n) => n + 1)}
      />

      {ranking && <SourceBanner ranking={ranking} />}
      {feedbackError && <p className="text-xs text-[#9A5A3C]">{feedbackError}</p>}

      {error ? (
        <div className="rounded-2xl border border-[#E2E0D8] bg-white p-10 text-center text-sm text-[#8C8A82]">Gap agent unavailable: {error}</div>
      ) : nothingToAnalyse ? (
        <div className="rounded-2xl border border-[#E2E0D8] bg-white p-10 text-center">
          <p className="text-3xl" aria-hidden="true">🧺</p>
          <h2 className="mt-2 font-display text-[22px] font-semibold text-[#1C1C1C]">Nothing to analyse yet</h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-[#8C8A82]">
            Add pieces to My Wardrobe and your gaps will appear here, ranked for each context.
          </p>
        </div>
      ) : (
        <div className="grid min-h-0 grid-cols-1 gap-3.5 lg:flex-1 lg:grid-cols-[minmax(300px,380px)_1fr]">
          <div className="flex max-h-[60vh] min-h-0 flex-col lg:max-h-none [&>section]:min-h-0 [&>section]:flex-1">
            <GapList
              gaps={ranking?.ranked_gaps ?? null}
              covered={ranking?.covered ?? []}
              notAnalysed={ranking?.not_analysed}
              selectedId={selectedId}
              isDismissed={isDismissed}
              isConfirmed={isConfirmed}
              thumbs={thumbs}
              onSelect={setSelectedId}
            />
          </div>

          {ranking && selected ? (
            <GapDetail
              goal={goal}
              gap={selected}
              currentCoverage={score ?? 0}
              coverageAfter={coverage(ranking.ranked_gaps, ranking.covered, selected.candidate_id)}
              confirmed={isConfirmed(selected.candidate_id)}
              dismissed={isDismissed(selected.candidate_id)}
              onConfirm={() => confirm(selected)}
              onDismiss={() => dismiss(selected)}
              onRestore={() => restore(selected)}
              onAsk={() =>
                ask(`Tell me more about the "${selected.name}" gap for ${goalLabel.toLowerCase()}. Why is it ranked #${selectedIndex + 1}?`)
              }
              onPhotosLoaded={(photos) => rememberPhoto(selected, photos)}
            />
          ) : (
            <section className="grid place-items-center rounded-2xl border border-[#E2E0D8] bg-white p-10 text-center text-[#8C8A82]">
              {ranking ? (
                <div>
                  <p className="text-2xl text-[#556B2F]" aria-hidden="true">✓</p>
                  <h2 className="mt-2 text-sm font-semibold text-[#1C1C1C]">No missing pieces for this context</h2>
                  <p className="mt-1 text-xs">Try another context from the bar above.</p>
                </div>
              ) : (
                <p className="text-sm">Analysing your wardrobe…</p>
              )}
            </section>
          )}
        </div>
      )}

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
