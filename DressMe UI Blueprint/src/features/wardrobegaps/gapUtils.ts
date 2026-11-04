// Shared constants and helpers of the Wardrobe Gaps page.
import { useState } from "react";
import type { CoveredRequirement, RankedGap } from "./api";

export const GOAL_DESIGN: Record<string, { icon: string; short: string; note: string; prompt: string }> = {
  winter_work: { icon: "❄", short: "Winter work", note: "Office days, rain & cold", prompt: "What am I missing for winter work days in Tunis?" },
  summer_casual: { icon: "☀", short: "Summer", note: "Light & breathable", prompt: "What am I missing for hot summer days?" },
  formal_event: { icon: "✦", short: "Formal", note: "Weddings & celebrations", prompt: "What am I missing for a summer wedding?" },
  sport_gym: { icon: "⚡", short: "Gym", note: "Training, running & the gym", prompt: "What am I missing for the gym and sport?" },
  hiking_outdoor: { icon: "▲", short: "Hiking", note: "Trails, wind & rain", prompt: "What am I missing for hiking and the outdoors?" },
  beach_pool: { icon: "≈", short: "Beach", note: "Swim, sun & sand", prompt: "What am I missing for a beach or pool day?" },
  dinner_date: { icon: "✧", short: "Dinner", note: "Evenings out", prompt: "What am I missing for a dinner or date night?" },
  daily_basics: { icon: "◇", short: "Basics", note: "Socks, belt, scarf, gloves, umbrella", prompt: "What everyday basics am I missing?" },
};

export const FEATURES: { key: keyof RankedGap; label: string; inverse?: boolean }[] = [
  { key: "coverage_deficit", label: "Coverage deficit" },
  { key: "use_frequency", label: "Use frequency" },
  { key: "season_relevance", label: "Season relevance" },
  { key: "outfit_gain", label: "Outfit gain" },
  { key: "preference_match", label: "Preference match" },
  { key: "redundancy_score", label: "Redundancy (lower is better)", inverse: true },
];

export const PRIORITY_STYLE = {
  high: "bg-[#F5E6DC] text-[#9A5A3C]",
  medium: "bg-[#F4EEDD] text-[#8A7130]",
  low: "bg-[#E8EDE0] text-[#556B2F]",
};

// "I need this" (3) / "Not relevant" (0) labels live on the server, per user: the ranking brings them back
// (RankedGap.feedback), so they follow the account to any browser or device and never leak to another account.
// This hook only keeps the buttons instant: a click shows at once, and the server answer confirms or reverts it.
export type Label = 0 | 3 | null;

export function useFeedbackLabels() {
  const [labels, setLabels] = useState<Record<string, Label>>({});

  // Replace the labels of one goal with what the server says (a fresh ranking), leaving other goals alone.
  const syncFromRanking = (goal: string, gaps: RankedGap[]) =>
    setLabels((current) => {
      const next = Object.fromEntries(Object.entries(current).filter(([key]) => !key.startsWith(`${goal}:`)));
      for (const gap of gaps) if (gap.feedback != null) next[feedbackKey(goal, gap.candidate_id)] = gap.feedback;
      return next;
    });

  const set = (key: string, label: Label) => setLabels((current) => ({ ...current, [key]: label }));
  const labelOf = (key: string): Label => labels[key] ?? null;
  return { labelOf, set, syncFromRanking };
}

// The old versions kept these two lists in the browser, shared by every account that used it. The server has the
// labels that mattered (each click was already sent), so the leftovers are simply removed.
export function clearLegacyFeedbackStorage() {
  try {
    localStorage.removeItem("dressme.bo3.dismissed");
    localStorage.removeItem("dressme.bo3.confirmed");
  } catch {
    // Storage can be blocked: nothing to clean then.
  }
}

// Coverage = owned units / required units across every requirement of the goal.
export function coverage(gaps: RankedGap[], covered: CoveredRequirement[], filled?: string) {
  const all = [...gaps, ...covered];
  const required = all.reduce((t, r) => t + r.required_count, 0);
  const owned = all.reduce(
    (t, r) => t + (r.candidate_id === filled ? r.required_count : Math.min(r.owned_count, r.required_count)),
    0,
  );
  return required ? Math.round((owned / required) * 100) : 0;
}

export function reasonFor(gap: RankedGap) {
  const ownership =
    gap.owned_count === 0 ? "Nothing in your wardrobe covers this yet" : `You own ${gap.owned_count} of the ${gap.required_count} needed`;
  const strongest = FEATURES.filter((f) => !f.inverse && f.key !== "coverage_deficit")
    .sort((a, b) => (gap[b.key] as number) - (gap[a.key] as number))[0];
  return `${ownership}. Strongest signal: ${strongest.label.toLowerCase()} (${(gap[strongest.key] as number).toFixed(2)}).`;
}

// Key of a gap in the local feedback lists: the same piece can be a gap in several contexts.
export const feedbackKey = (goal: string, candidateId: string) => `${goal}:${candidateId}`;
