import catalog from "./garments.json"

export type GarmentSlot = "top" | "bottom" | "outerwear" | "shoes" | "dress"

export type GarmentId =
  | "tshirt"
  | "oxford"
  | "turtleneck"
  | "trousers"
  | "jeans"
  | "shorts"
  | "skirt"
  | "dress"
  | "cardigan"
  | "jacket"
  | "blazer"
  | "boots"

export type GarmentMeta = {
  id: GarmentId
  label: string
  slot: GarmentSlot
  swatch: string
  hint: string
  wardrobeIds: number[]
}

export const GARMENTS: GarmentMeta[] = catalog.garments.map((g) => ({
  id: g.id as GarmentId,
  label: g.label,
  slot: g.slot as GarmentSlot,
  swatch: g.swatch,
  hint: g.hint,
  wardrobeIds: g.wardrobeIds,
}))

export const SLOT_ORDER: GarmentSlot[] = ["top", "bottom", "dress", "outerwear", "shoes"]

export const SLOT_LABELS: Record<GarmentSlot, string> = {
  top: "Tops",
  bottom: "Bottoms",
  dress: "Dresses",
  outerwear: "Outerwear",
  shoes: "Shoes",
}

const GARMENT_BY_ID = new Map(GARMENTS.map((g) => [g.id, g]))

export function garmentById(id: GarmentId): GarmentMeta | undefined {
  return GARMENT_BY_ID.get(id)
}

export function garmentsForSlot(slot: GarmentSlot): GarmentMeta[] {
  return GARMENTS.filter((g) => g.slot === slot)
}

function slotRank(slot: GarmentSlot): number {
  const index = SLOT_ORDER.indexOf(slot)
  return index === -1 ? SLOT_ORDER.length : index
}

export function sortSelection(selection: GarmentId[]): GarmentId[] {
  return [...selection].sort((a, b) => {
    const ga = garmentById(a)
    const gb = garmentById(b)
    if (!ga || !gb) return 0
    return slotRank(ga.slot) - slotRank(gb.slot)
  })
}

export function toggleGarment(current: GarmentId[], id: GarmentId): GarmentId[] {
  const next = garmentById(id)
  if (!next) return current
  if (current.includes(id)) return current.filter((g) => g !== id)

  const kept = current.filter((existingId) => {
    const existing = garmentById(existingId)
    if (!existing) return false
    if (existing.slot === next.slot) return false
    if (next.slot === "dress" && (existing.slot === "top" || existing.slot === "bottom")) return false
    if ((next.slot === "top" || next.slot === "bottom") && existing.slot === "dress") return false
    return true
  })

  return sortSelection([...kept, id])
}

export function clearSlot(current: GarmentId[], slot: GarmentSlot): GarmentId[] {
  return current.filter((id) => garmentById(id)?.slot !== slot)
}

export function selectionLabel(selection: GarmentId[]): string {
  if (selection.length === 0) return "Body only (no garments)"
  return selection.map((id) => garmentById(id)?.label ?? id).join(" + ")
}

export function wardrobeIdsForSelection(selection: GarmentId[]): number[] {
  return selection.flatMap((id) => garmentById(id)?.wardrobeIds ?? [])
}
