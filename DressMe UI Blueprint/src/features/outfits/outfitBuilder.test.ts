import { describe, expect, it } from "vitest"
import type { WardrobeItem } from "../../lib/types"
import { buildOutfits, currentSeason, harmony } from "./outfitBuilder"

let counter = 0
function item(group: string, extra: Partial<WardrobeItem> = {}): WardrobeItem {
  counter += 1
  return {
    id: `item-${counter}`,
    name: `${group} ${counter}`,
    category: group.toLowerCase(),
    category_group: group,
    color_family: "neutral",
    occasions: ["work"],
    seasons: ["winter"],
    ...extra,
  }
}

const request = { occasion: "work", season: "winter" }

describe("harmony", () => {
  it("lets neutrals go with anything and rejects two loud colours", () => {
    expect(harmony("neutral", "bright")).toBeGreaterThan(0)
    expect(harmony("bright", "bright")).toBeLessThan(0)
    expect(harmony("warm", "cool")).toBeLessThan(0)
    expect(harmony(null, "warm")).toBe(0)
  })
})

describe("buildOutfits", () => {
  it("composes top, bottom, shoes and a layer in winter", () => {
    const wardrobe = [item("Tops"), item("Bottoms"), item("Shoes"), item("Outerwear")]
    const { outfits, missing } = buildOutfits(wardrobe, request)
    expect(missing).toEqual([])
    expect(outfits).toHaveLength(1)
    expect(outfits[0].items.map((entry) => entry.category_group).sort()).toEqual([
      "Bottoms",
      "Outerwear",
      "Shoes",
      "Tops",
    ])
  })

  it("does not add a coat in summer", () => {
    const wardrobe = [
      item("Tops", { seasons: ["summer"] }),
      item("Bottoms", { seasons: ["summer"] }),
      item("Outerwear", { seasons: ["winter"] }),
    ]
    const { outfits, missing } = buildOutfits(wardrobe, { occasion: "work", season: "summer" })
    expect(outfits[0].items.some((entry) => entry.category_group === "Outerwear")).toBe(false)
    expect(missing).toEqual(["shoes"])
  })

  it("names what is missing instead of inventing outfits", () => {
    expect(buildOutfits([item("Tops")], request).outfits).toHaveLength(0)
    expect(buildOutfits([item("Tops")], request).missing).toContain("a bottom")
    expect(buildOutfits([], request).missing).toContain("shoes")
  })

  it("prefers pieces made for the occasion and the season", () => {
    const right = item("Tops", { occasions: ["work"], seasons: ["winter"] })
    const wrong = item("Tops", { occasions: ["beach"], seasons: ["summer"] })
    const { outfits } = buildOutfits([wrong, right, item("Bottoms"), item("Shoes"), item("Outerwear")], request, 1)
    expect(outfits[0].items.map((entry) => entry.id)).toContain(right.id)
  })

  it("offers different outfits and changes them with the shuffle number", () => {
    const wardrobe = [
      item("Tops"), item("Tops"), item("Tops"),
      item("Bottoms"), item("Bottoms"),
      item("Shoes"), item("Shoes"),
      item("Outerwear"), item("Outerwear"),
    ]
    const first = buildOutfits(wardrobe, request, 3)
    const tops = first.outfits.map((outfit) => outfit.items[0].id)
    expect(new Set(tops).size).toBe(3)
    expect(buildOutfits(wardrobe, request, 3)).toEqual(first) // same seed, same outfits
    const shuffled = buildOutfits(wardrobe, request, 3, 7)
    expect(shuffled.outfits.map((outfit) => outfit.items.map((entry) => entry.id).join())).not.toEqual(
      first.outfits.map((outfit) => outfit.items.map((entry) => entry.id).join()),
    )
  })

  it("uses a dress as a complete base", () => {
    const { outfits } = buildOutfits([item("Dresses"), item("Shoes")], request)
    expect(outfits[0].items.map((entry) => entry.category_group)).toEqual(["Dresses", "Shoes"])
  })
})

describe("currentSeason", () => {
  it("maps months to seasons", () => {
    expect(currentSeason(new Date(2026, 0, 15))).toBe("winter")
    expect(currentSeason(new Date(2026, 3, 15))).toBe("spring")
    expect(currentSeason(new Date(2026, 6, 15))).toBe("summer")
    expect(currentSeason(new Date(2026, 9, 15))).toBe("autumn")
  })
})
