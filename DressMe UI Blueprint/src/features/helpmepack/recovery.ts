import type { DailyRequirement, MissingItemRecommendation } from "../../api/tripAgent";

/** Convert older service diagnostics to the same structured cards as current responses. */
export function recoveryItems(
  missingItems: MissingItemRecommendation[] | undefined,
  suggestions: string[],
): MissingItemRecommendation[] {
  if (missingItems !== undefined) return missingItems;

  const roles = new Map<string, Set<number>>();
  for (const suggestion of suggestions) {
    const match = suggestion.match(/day\(s\)\s*\[([\d,\s]+)\]\s*require the ['"]([\w-]+)['"] role/i);
    if (!match) continue;
    const days = roles.get(match[2].toLowerCase()) ?? new Set<number>();
    for (const day of match[1].split(",")) {
      const value = Number(day.trim());
      if (Number.isInteger(value) && value > 0) days.add(value);
    }
    roles.set(match[2].toLowerCase(), days);
  }

  const items: MissingItemRecommendation[] = [];
  const add = (key: string, title: string, examples: string[], covers: string[], note: string | null = null) => {
    const days = roles.get(key);
    if (days?.size) items.push({ key, title, examples, days: [...days].sort((a, b) => a - b), covers, note });
  };

  if (roles.has("rain")) {
    const rainDays = roles.get("rain")!;
    for (const day of roles.get("outerwear") ?? []) rainDays.add(day);
    add("rain", "Add a waterproof outer layer", ["Waterproof raincoat", "Waterproof rain jacket"],
      roles.has("outerwear") ? ["rain protection", "outerwear"] : ["rain protection"],
      "If you already own one, check its category and describe it as waterproof or a raincoat.");
  } else {
    add("outerwear", "Add an outer layer", ["Jacket", "Coat", "Cardigan"], ["outerwear"]);
  }
  add("warm", "Add a warm layer", ["Sweater", "Fleece", "Warm cardigan"], ["warm layer"]);
  add("sun", "Add sun protection", ["Sun hat", "Sunglasses"], ["sun protection"]);
  add("shoes", "Add a pair of shoes", ["Sneakers", "Closed-toe shoes"], ["shoes"]);
  add("top", "Add a top", ["T-shirt", "Shirt"], ["top"]);
  add("bottom", "Add a bottom", ["Trousers", "Skirt"], ["bottom"]);
  add("onepiece", "Add a dress or a top and bottom", ["Dress", "Top and trousers"], ["base outfit"]);
  return items;
}

export function dayLabels(days: number[]): string {
  const sorted = [...new Set(days)].sort((a, b) => a - b);
  if (!sorted.length) return "your trip";
  return `${sorted.length === 1 ? "Day" : "Days"} ${sorted.join(", ")}`;
}

export function recoveryReason(item: MissingItemRecommendation, requirements: DailyRequirement[]): string {
  const needed = dayLabels(item.days);
  const verb = item.days.length === 1 ? "needs" : "need";
  switch (item.key) {
    case "rain": {
      const rainyDays = requirements.filter((day) => item.days.includes(day.day_number)
        && (day.needs_rain_protection || day.weather.toLowerCase().includes("rain")))
        .map((day) => day.day_number);
      const rainNeeded = rainyDays.length ? rainyDays : item.days;
      return `${dayLabels(rainNeeded)} ${rainNeeded.length === 1 ? "needs" : "need"} rain protection. No suitable waterproof layer was found in your wardrobe.`;
    }
    case "outerwear": return `${needed} ${verb} an outer layer for the forecast, but none was found in your wardrobe.`;
    case "warm": return `${needed} ${verb} a warm layer for the forecast, but no sufficiently warm layer was found.`;
    case "sun": return `${needed} ${verb} sun protection, but no suitable hat or sunglasses were found.`;
    case "variety": return "The current wardrobe does not provide enough different complete outfits for every day.";
    case "shoes": return "Each outfit needs shoes, but no shoes were found in your wardrobe.";
    case "base_outfit":
    case "base_top":
    case "base_bottom": return "Each day needs a complete outfit: a dress, or a top and bottom, plus shoes.";
    default: return `${needed} ${verb} ${item.covers.join(" and ")}.`;
  }
}

export function readableSuggestion(suggestion: string): string {
  if (/no outfit can satisfy every hard/i.test(suggestion)) {
    return "Some days have no suitable outfit for the forecast and planned activities. Check the daily requirements below.";
  }
  return suggestion.replace(/\bDay\(s\)\s*\[([\d,\s]+)\]/gi, (_match, days: string) =>
    dayLabels(days.split(",").map(Number).filter(Number.isFinite)));
}
