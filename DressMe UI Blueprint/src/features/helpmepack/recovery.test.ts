import { describe, expect, it } from "vitest";
import type { DailyRequirement, MissingItemRecommendation } from "../../api/tripAgent";
import { dayLabels, readableSuggestion, recoveryItems, recoveryReason } from "./recovery";

const days: DailyRequirement[] = [
  { trip_id: "t", day_number: 1, date: "2027-06-01", activity: "walking", weather: "rainy",
    temperature_c: 15, precipitation_mm: 2, required_style: "casual", needs_outerwear: true,
    needs_warm_layer: false, needs_rain_protection: true, needs_sun_protection: false, activities: ["walking"] },
  { trip_id: "t", day_number: 2, date: "2027-06-02", activity: "walking", weather: "cloudy",
    temperature_c: 15, precipitation_mm: 0, required_style: "casual", needs_outerwear: true,
    needs_warm_layer: false, needs_rain_protection: false, needs_sun_protection: false, activities: ["walking"] },
];

describe("packing recovery explanations", () => {
  it("turns the older rain and outerwear messages into one actionable card", () => {
    const items = recoveryItems(undefined, [
      "Day(s) [1] require the 'rain' role, but the wardrobe has no item for it. To keep all hard constraints, add a genuinely waterproof raincoat in the wardrobe, or choose different dates/activities.",
      "Day(s) [1, 2] require the 'outerwear' role, but the wardrobe has no item for it.",
      "No outfit can satisfy every hard activity/style/weather constraint on day(s) [1, 2].",
    ]);
    expect(items).toHaveLength(1);
    expect(items[0].days).toEqual([1, 2]);
    expect(items[0].covers).toEqual(["rain protection", "outerwear"]);
    expect(recoveryReason(items[0], days)).toContain("Day 1 needs rain protection");
    expect(recoveryReason(items[0], days)).not.toContain("Day 2 needs rain protection");
  });

  it("uses structured recommendations without parsing stale messages", () => {
    const item: MissingItemRecommendation = {
      key: "warm", title: "Add a warm layer", days: [2], examples: ["Sweater"],
      covers: ["warm layer"], note: null,
    };
    expect(recoveryItems([item], ["Day(s) [1] require the 'rain' role"])).toEqual([item]);
    expect(recoveryItems([], ["Day(s) [1] require the 'rain' role"])).toEqual([]);
    expect(recoveryReason(item, days)).toContain("Day 2 needs a warm layer");
  });

  it("makes generic solver messages and day labels readable", () => {
    expect(dayLabels([3, 1, 3])).toBe("Days 1, 3");
    expect(readableSuggestion("No outfit can satisfy every hard activity/style/weather constraint on day(s) [1]."))
      .toContain("Check the daily requirements");
  });
});
