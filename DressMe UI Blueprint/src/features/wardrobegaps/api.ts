// Client for the BO3 gap agent API (backend/api.py), proxied by Vite under /api.
// Every request carries the signed-in user's Supabase session so BO3 loads their own wardrobe.
import { isSupabaseConfigured, supabase } from "../../lib/supabase";

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

// Where the analysed wardrobe came from. Anything but "supabase" is shown to the user as a banner.
export type WardrobeSource = {
  source: "supabase" | "sample" | "empty" | "error";
  item_count: number;
  reason: string;
  message: string | null;
};

export type GapRanking = {
  goal: string;
  goal_label?: string;
  season?: string;
  ranker_model?: string;
  ranker_trained_on?: string;
  wardrobe_source?: WardrobeSource;
  // "profile" = built from the user's own preferences, "default" = none filled in yet, "sample" = demo persona.
  profile_source?: "profile" | "default" | "sample" | null;
  ranked_gaps: RankedGap[];
  covered: CoveredRequirement[];
  note?: string;
};

export type TraceStep = { step: number; tool: string; arguments: Record<string, unknown>; result: unknown };

export type ChatTurn = { role: "user" | "assistant"; content: string };

// An owned piece the agent chose to show next to its answer.
export type ShownItem = {
  id: string;
  name: string;
  category: string;
  subcategory?: string | null;
  colors?: string[];
  image_url?: string | null;
};

export type ChatResponse = {
  conversation_id: string;
  answer: string;
  ranking: GapRanking | null;
  trace: TraceStep[];
  items: ShownItem[];
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (isSupabaseConfigured) {
    const { data } = await supabase.auth.getSession();
    if (data.session?.access_token) headers.set("Authorization", `Bearer ${data.session.access_token}`);
  }
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const fetchGoals = () => request<Goal[]>("/api/bo3/goals");

// The GPT interpretation (+5 s) is not shown by any screen, so it is not requested by default.
export const fetchGaps = (goal: string, interpret = false) =>
  request<GapRanking>(`/api/bo3/gaps?goal=${encodeURIComponent(goal)}&interpret=${interpret}`);

// A web photo of a missing piece. Show `thumbnail` (stable copy) and link to `page_url` (the source shop).
export type WebPhoto = { title: string; thumbnail: string; image_url: string | null; page_url: string; source: string };
export type GapPhotosResponse = { candidate_id: string; piece: string; images: WebPhoto[]; cached: boolean; message: string | null };

// Loaded per card, after the ranking is shown: each web search takes about a second.
export const fetchGapImages = (goal: string, candidateId: string, limit = 3) =>
  request<GapPhotosResponse>(
    `/api/bo3/gaps/${encodeURIComponent(candidateId)}/images?goal=${encodeURIComponent(goal)}&limit=${limit}`,
  );

const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

// relevance: 3 = "I need this", 0 = "Not relevant", null = remove the label.
export const sendFeedback = (goal: string, candidateId: string, relevance: 0 | 3 | null) =>
  post<LearningStatus>("/api/bo3/feedback", { goal, candidate_id: candidateId, relevance });

export const sendChat =(message: string, history: ChatTurn[], conversationId: string | null) =>
  request<ChatResponse>("/api/bo3/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history, conversation_id: conversationId }),
  });
