import type { WardrobeItem } from "../../lib/types"

export type Outfit = {
  items: WardrobeItem[]
  score: number
  why: string[]
  /** Set by the agent: the name of the look and how it answers the forecast. */
  title?: string
  weatherNote?: string
}

export type OutfitRequest = { occasion: string; season: string }

export type OutfitResult = {
  outfits: Outfit[]
  // Slots the wardrobe cannot fill for this request ("shoes", "a top"...): the page links them to shopping.
  missing: string[]
}

const NEUTRAL_FAMILIES = ["neutral", "earth", "metallic"]
const COLD_SEASONS = ["autumn", "winter"]
const POOL = 10 // best pieces kept per slot: enough variety without trying every combination

/** How well two colour families sit together: neutrals go with everything, two loud colours clash. */
export function harmony(a?: string | null, b?: string | null): number {
  if (!a || !b) return 0
  if (NEUTRAL_FAMILIES.includes(a) || NEUTRAL_FAMILIES.includes(b)) return 2
  if (a === b) return a === "bright" ? -1 : 1.5
  if (a === "multicolor" || b === "multicolor") return -1
  if (a === "bright" || b === "bright") return -2
  if ((a === "warm" && b === "cool") || (a === "cool" && b === "warm")) return -1
  return 0.5
}

function fits(item: WardrobeItem, { occasion, season }: OutfitRequest) {
  const occasions = item.occasions ?? []
  const seasons = item.seasons ?? []
  return {
    occasion: occasions.includes(occasion),
    season: seasons.length === 0 || seasons.includes(season),
  }
}

function pieceScore(item: WardrobeItem, request: OutfitRequest) {
  const match = fits(item, request)
  return (match.occasion ? 3 : 0) + (match.season ? 2 : -3)
}

// A small deterministic generator: the same "shuffle" number always gives the same outfits.
function jitter(seed: number, key: string) {
  let hash = seed * 2654435761
  for (let index = 0; index < key.length; index++) hash = (hash ^ key.charCodeAt(index)) * 16777619
  return ((hash >>> 0) % 1000) / 1000
}

function best(items: WardrobeItem[], request: OutfitRequest, seed: number) {
  return [...items]
    .map((item) => ({ item, score: pieceScore(item, request) + jitter(seed, item.id) * (seed ? 2.5 : 0) }))
    .sort((a, b) => b.score - a.score)
    .slice(0, POOL)
    .map((entry) => entry.item)
}

function describe(outfit: WardrobeItem[], request: OutfitRequest): string[] {
  const why: string[] = []
  const onOccasion = outfit.filter((item) => fits(item, request).occasion).length
  if (onOccasion === outfit.length) why.push(`Every piece suits ${request.occasion}`)
  else if (onOccasion > 0) why.push(`${onOccasion} of ${outfit.length} pieces suit ${request.occasion}`)
  const families = outfit.map((item) => item.color_family)
  if (families.every((family) => family && NEUTRAL_FAMILIES.includes(family))) why.push("Easy neutral palette")
  else if (outfit.some((item) => item.category_group === "Outerwear" || item.category_group === "Tops")) {
    const pairs = outfit.slice(1).map((item) => harmony(outfit[0].color_family, item.color_family))
    if (pairs.length && Math.min(...pairs) >= 1) why.push("Colours go well together")
  }
  if (outfit.some((item) => item.category_group === "Outerwear")) why.push(`Extra layer for ${request.season}`)
  return why
}

function overlap(a: WardrobeItem[], b: WardrobeItem[]) {
  return a.filter((item) => b.some((other) => other.id === item.id)).length
}

/** Compose outfits from the wardrobe for an occasion and a season. Pure and deterministic for a given seed. */
export function buildOutfits(
  items: WardrobeItem[],
  request: OutfitRequest,
  count = 3,
  seed = 0,
): OutfitResult {
  const group = (name: string) => items.filter((item) => item.category_group === name)
  const tops = best(group("Tops"), request, seed)
  const bottoms = best(group("Bottoms"), request, seed)
  const dresses = best(group("Dresses"), request, seed)
  const shoes = best(group("Shoes"), request, seed)
  const layers = COLD_SEASONS.includes(request.season) ? best(group("Outerwear"), request, seed) : []

  const missing: string[] = []
  if (!dresses.length && (!tops.length || !bottoms.length)) {
    missing.push(!tops.length ? "a top" : "a bottom")
  }
  if (!shoes.length) missing.push("shoes")
  if (COLD_SEASONS.includes(request.season) && !layers.length) missing.push("a warm layer")

  const bases: WardrobeItem[][] = [
    ...tops.flatMap((top) => bottoms.map((bottom) => [top, bottom])),
    ...dresses.map((dress) => [dress]),
  ]

  const candidates: Outfit[] = bases.map((base) => {
    const extras: WardrobeItem[] = []
    let score = base.reduce((sum, item) => sum + pieceScore(item, request), 0)
    if (base.length === 2) score += harmony(base[0].color_family, base[1].color_family)

    const shoe = shoes
      .map((candidate) => ({
        candidate,
        value: pieceScore(candidate, request) + harmony(base[base.length - 1].color_family, candidate.color_family),
      }))
      .sort((a, b) => b.value - a.value)[0]
    if (shoe) {
      extras.push(shoe.candidate)
      score += shoe.value
    }
    const layer = layers
      .map((candidate) => ({
        candidate,
        value: pieceScore(candidate, request) + harmony(base[0].color_family, candidate.color_family),
      }))
      .sort((a, b) => b.value - a.value)[0]
    if (layer) {
      extras.push(layer.candidate)
      score += layer.value
    }
    const outfit = [...base, ...extras]
    return { items: outfit, score: score + jitter(seed, outfit.map((item) => item.id).join()) * (seed ? 2 : 0), why: [] }
  })

  // Greedy pick: highest score first, but an outfit that reuses what is already chosen loses points,
  // so the three suggestions look different from each other.
  const chosen: Outfit[] = []
  const pool = [...candidates]
  while (chosen.length < count && pool.length) {
    pool.sort(
      (a, b) =>
        b.score - chosen.reduce((sum, picked) => sum + overlap(b.items, picked.items) * 2, 0) -
        (a.score - chosen.reduce((sum, picked) => sum + overlap(a.items, picked.items) * 2, 0)),
    )
    const next = pool.shift()
    if (next) chosen.push({ ...next, why: describe(next.items, request) })
  }

  return { outfits: chosen, missing }
}

export function currentSeason(date = new Date()): string {
  const month = date.getMonth()
  if (month >= 2 && month <= 4) return "spring"
  if (month >= 5 && month <= 7) return "summer"
  if (month >= 8 && month <= 10) return "autumn"
  return "winter"
}
