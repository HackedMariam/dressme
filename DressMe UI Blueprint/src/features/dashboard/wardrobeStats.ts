import type { WardrobeItem } from "../../lib/types"

export function wardrobeStats(items: WardrobeItem[]) {
  const confidences = items
    .map((item) => item.confidence)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value))
  const groups = new Set(items.map((item) => item.category_group?.trim()).filter(Boolean))
  const matches = new Map<string, { category: string; color: string; items: WardrobeItem[] }>()

  for (const item of items) {
    const category = item.category?.trim()
    const color = item.color_name?.trim()
    if (!category || !color) continue
    const key = JSON.stringify([category.toLowerCase(), color.toLowerCase()])
    const group = matches.get(key) ?? { category, color, items: [] }
    group.items.push(item)
    matches.set(key, group)
  }

  return {
    categoryCount: groups.size,
    toReview: items.filter((item) => item.needs_review).length,
    confirmed: items.filter((item) => item.status === "confirmed").length,
    avgConfidence: confidences.length
      ? confidences.reduce((sum, value) => sum + value, 0) / confidences.length
      : null,
    confidenceCount: confidences.length,
    overlaps: [...matches.values()].filter((group) => group.items.length > 1)
      .sort((a, b) => b.items.length - a.items.length),
  }
}
