// Shared constants and helpers of the Wardrobe Gaps page.
import { useEffect, useState } from "react";
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

export const useDismissedList = () => usePersistentList(DISMISSED_KEY);
export const useConfirmedList = () => usePersistentList(CONFIRMED_KEY);

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
