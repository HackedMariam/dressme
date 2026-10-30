import { describe, expect, it } from "vitest"
import type { WardrobeItem } from "../../lib/types"
import { wardrobeStats } from "./wardrobeStats"

function item(id: string, fields: Partial<WardrobeItem> = {}): WardrobeItem {
  return { id, name: id, category: "top", category_group: "Tops", ...fields }
}

describe("wardrobeStats", () => {
  it("averages only available confidence values and counts real item statuses", () => {
    const result = wardrobeStats([
      item("a", { confidence: 0.8, needs_review: true }),
      item("b", { confidence: null, status: "confirmed", category_group: "Shoes" }),
      item("c", { confidence: 0.4 }),
    ])
    expect(result.avgConfidence).toBeCloseTo(0.6)
    expect(result.confidenceCount).toBe(2)
    expect(result.categoryCount).toBe(2)
    expect(result.toReview).toBe(1)
    expect(result.confirmed).toBe(1)
    expect(wardrobeStats([]).avgConfidence).toBeNull()
  })

  it("only groups items with the same known category and colour", () => {
    const result = wardrobeStats([
      item("a", { color_name: "Navy" }),
      item("b", { color_name: "navy" }),
      item("c", { category: "pants", color_name: "navy" }),
      item("d", { color_name: null }),
      item("e", { color_name: null }),
    ])
    expect(result.overlaps).toHaveLength(1)
    expect(result.overlaps[0].items.map((entry) => entry.id)).toEqual(["a", "b"])
  })
})
