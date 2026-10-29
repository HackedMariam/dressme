import mapping from "./tryon_mapping.json"
import {
  SLOT_ORDER,
  garmentById,
  type GarmentId,
  type GarmentSlot,
} from "./garments"

export type WardrobeItemLike = {
  id: string
  name: string
  category: string
  category_group?: string | null
  subcategory?: string | null
  color_hex?: string | null
  material?: string | null
  formality?: number | null
  cutout_url?: string | null
  back_photo_url?: string | null
  image_url?: string | null
  mesh_url?: string | null
  mesh_version?: number | null
}

export type TryOnItem = {
  wardrobeId: string
  templateId: GarmentId
  slot: GarmentSlot
  label: string
  colorHex: string
  cutoutUrl: string | null
  backPhotoUrl: string | null
  meshUrl: string | null
  meshVersion: number
  category: string
  categoryGroup: string
  subcategory: string | null
  material: string | null
  formality: number | null
}

export type TryOnItemSnapshot = {
  wardrobe_item_id: string
  template: GarmentId
  slot: GarmentSlot
  label: string
  color_hex: string
  cutout_url?: string | null
  back_photo_url?: string | null
  mesh_url?: string | null
  mesh_version?: number | null
  category?: string
}

export type WardrobeItemPayload = {
  wardrobe_item_id: string
  template: GarmentId
  slot: GarmentSlot
  label: string
  color_hex: string
  cutout_url?: string | null
  mesh_url?: string | null
  mesh_version?: number
  category: string
}

type CategoryRule = {
  default?: string
  formal?: string
  denim?: string
}

const CATEGORY_RULES = mapping.categories as Record<string, CategoryRule>
const GROUP_RULES = mapping.groups as Record<string, string>
const UNSUPPORTED = new Set((mapping.unsupported ?? []) as string[])
const DEFAULT_COLOR = "#9a9a9a"

function cleanHex(value: string | null | undefined): string {
  return typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value.trim())
    ? value.trim()
    : DEFAULT_COLOR
}

export function resolveTryOnItem(item: WardrobeItemLike): TryOnItem | null {
  const category = String(item.category ?? "").trim().toLowerCase()
  const group = String(item.category_group ?? "").trim().toLowerCase()
  const text = [item.name, item.subcategory, item.material]
    .filter(Boolean)
    .join(" ")
    .toLowerCase()
  if (UNSUPPORTED.has(category)) return null
  const rule = CATEGORY_RULES[category]
  const formal = Number(item.formality ?? 0) >= Number(mapping.formal_at ?? 4)

  let template = rule?.default
  if (rule?.formal && formal) template = rule.formal
  if (rule?.denim && /denim|jean/.test(text)) template = rule.denim
  if (!template && !rule && group) template = GROUP_RULES[group]
  if (!template) return null

  const meta = garmentById(template as GarmentId)
  if (!meta) return null

  return {
    wardrobeId: item.id,
    templateId: meta.id,
    slot: meta.slot,
    label: item.name?.trim() || meta.label,
    colorHex: cleanHex(item.color_hex),
    cutoutUrl: item.cutout_url || item.image_url || null,
    backPhotoUrl: item.back_photo_url || null,
    meshUrl: item.mesh_url || null,
    meshVersion: Number(item.mesh_version ?? 0),
    category,
    categoryGroup: group,
    subcategory: item.subcategory ?? null,
    material: item.material ?? null,
    formality: item.formality ?? null,
  }
}

export function tryOnItemsFromSnapshots(
  snapshots: TryOnItemSnapshot[] | null | undefined,
): TryOnItem[] {
  if (!Array.isArray(snapshots)) return []
  const seen = new Set<string>()
  const items: TryOnItem[] = []
  for (const snapshot of snapshots) {
    if (!snapshot || typeof snapshot.wardrobe_item_id !== "string") continue
    if (seen.has(snapshot.wardrobe_item_id)) continue
    const meta = garmentById(snapshot.template)
    if (!meta) continue
    seen.add(snapshot.wardrobe_item_id)
    items.push({
      wardrobeId: snapshot.wardrobe_item_id,
      templateId: meta.id,
      slot: snapshot.slot ?? meta.slot,
      label: snapshot.label || meta.label,
      colorHex: cleanHex(snapshot.color_hex),
      cutoutUrl: snapshot.cutout_url ?? null,
      backPhotoUrl: snapshot.back_photo_url ?? null,
      meshUrl: snapshot.mesh_url ?? null,
      meshVersion: Number(snapshot.mesh_version ?? 0),
      category: snapshot.category ?? "",
      categoryGroup: "",
      subcategory: null,
      material: null,
      formality: null,
    })
  }
  return sortTryOnItems(items)
}

export function sortTryOnItems(items: TryOnItem[]): TryOnItem[] {
  return [...items].sort(
    (a, b) => SLOT_ORDER.indexOf(a.slot) - SLOT_ORDER.indexOf(b.slot),
  )
}

function conflicts(a: TryOnItem, b: TryOnItem): boolean {
  if (a.slot === b.slot) return true
  if (a.slot === "dress" && (b.slot === "top" || b.slot === "bottom")) return true
  if (b.slot === "dress" && (a.slot === "top" || a.slot === "bottom")) return true
  return false
}

export function toggleTryOnItem(
  current: TryOnItem[],
  item: TryOnItem,
): TryOnItem[] {
  if (current.some((entry) => entry.wardrobeId === item.wardrobeId)) {
    return current.filter((entry) => entry.wardrobeId !== item.wardrobeId)
  }
  const kept = current.filter((entry) => !conflicts(entry, item))
  return sortTryOnItems([...kept, item])
}

export function clearTryOnSlot(
  current: TryOnItem[],
  slot: GarmentSlot,
): TryOnItem[] {
  return current.filter((item) => item.slot !== slot)
}

export function tryOnLabel(selection: TryOnItem[]): string {
  if (selection.length === 0) return "Body only (no garments)"
  return selection.map((item) => item.label).join(" + ")
}

export function tryOnSnapshots(selection: TryOnItem[]): TryOnItemSnapshot[] {
  return selection.map((item) => ({
    wardrobe_item_id: item.wardrobeId,
    template: item.templateId,
    slot: item.slot,
    label: item.label,
    color_hex: item.colorHex,
    cutout_url: item.cutoutUrl,
    back_photo_url: item.backPhotoUrl,
    mesh_url: item.meshUrl,
    mesh_version: item.meshVersion,
    category: item.category,
  }))
}

export function tryOnPayload(selection: TryOnItem[]): WardrobeItemPayload[] {
  return selection.map((item) => ({
    wardrobe_item_id: item.wardrobeId,
    template: item.templateId,
    slot: item.slot,
    label: item.label,
    color_hex: item.colorHex,
    cutout_url: item.cutoutUrl,
    mesh_url: item.meshUrl,
    mesh_version: item.meshVersion,
    category: item.category,
  }))
}
