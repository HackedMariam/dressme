// Client for the BO3 gap agent API (backend/api.py), proxied by Vite under /api.
import { supabase } from "../../lib/supabase";

export type Goal = { id: string; label: string; season: string };

export type RankedGap = {
  rank: number;
  candidate_id: string;
  name: string;
  priority: "high" | "medium" | "low";
  ranking_score: number;
  owned_count: number;
  required_count: number;
  matched_items: string[];
  suggested_item: string;
  coverage_deficit: number;
  use_frequency: number;
  season_relevance: number;
  outfit_gain: number;
  preference_match: number;
  redundancy_score: number;
  closest_owned_item: string;
  pairable_owned_items: number;
};

export type TrainingRun = {
  trained_at: string;
  previous_model: string;
  synthetic_groups: number;
  feedback_groups: number;
  explicit_labels: number;
  real_group_weight: number;
  ndcg_at_3_before: number | null;
  ndcg_at_3_after: number | null;
  evaluation: string;
};

export type LearningStatus = {
  active_model: string;
  personalised: boolean;
  feedback_labels: number;
  need_labels: number;
  not_relevant_labels: number;
  goals_with_feedback: string[];
  last_training: TrainingRun | null;
};

export type CoveredRequirement = {
  candidate_id: string;
  name: string;
  owned_count: number;
  required_count: number;
  matched_items: string[];
};

export type GapRanking = {
  goal: string;
  goal_label?: string;
  season?: string;
  ranker_model?: string;
  ranker_trained_on?: string;
  ranked_gaps: RankedGap[];
  covered: CoveredRequirement[];
  note?: string;
};

export type TraceStep = { step: number; tool: string; arguments: Record<string, unknown>; result: unknown };

export type ChatTurn = { role: "user" | "assistant"; content: string };

export type ChatResponse = {
  conversation_id: string;
  answer: string;
  ranking: GapRanking | null;
  trace: TraceStep[];
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const { data, error } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (error || !token) throw new Error("Please sign in to use Wardrobe Gaps.");
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(path, { ...init, headers });
  } catch {
    throw new Error("Cannot reach the Wardrobe Gaps service. Make sure it is running.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const fetchGoals = () => request<Goal[]>("/api/bo3/goals");

export const fetchGaps = (goal: string) => request<GapRanking>(`/api/bo3/gaps?goal=${encodeURIComponent(goal)}`);

const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

// relevance: 3 = "I need this", 0 = "Not relevant", null = remove the label.
export const sendFeedback = (goal: string, candidateId: string, relevance: 0 | 3 | null) =>
  post<LearningStatus>("/api/bo3/feedback", { goal, candidate_id: candidateId, relevance });

export const fetchLearning = () => request<LearningStatus>("/api/bo3/learning");

export const retrainRanker = () => post<{ training: TrainingRun; status: LearningStatus }>("/api/bo3/retrain");

export const resetRanker = () => post<LearningStatus>("/api/bo3/reset-model");

export const sendChat =(message: string, history: ChatTurn[], conversationId: string | null) =>
  request<ChatResponse>("/api/bo3/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history, conversation_id: conversationId }),
  });
