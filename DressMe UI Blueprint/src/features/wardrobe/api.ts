import type { WardrobeItemRow } from "../../lib/database.types"
import { supabase } from "../../lib/supabase"

const BASE_COLUMNS = [
  "id",
  "user_id",
  "name",
  "category",
  "category_group",
  "subcategory",
  "color_name",
  "color_hex",
  "colors",
  "pattern",
  "material",
  "seasons",
  "style",
  "occasions",
  "formality",
  "warmth",
  "description",
  "styling_tips",
  "tags",
  "confidence",
  "field_confidence",
  "needs_review",
  "status",
  "image_url",
  "cutout_url",
  "zone",
  "position_3d",
  "detection",
  "predicted",
  "enrichment_source",
  "created_at",
]

const MESH_COLUMNS = [
  "mesh_url",
  "mesh_status",
  "mesh_source",
  "mesh_version",
  "mesh_meta",
  "mesh_error",
]

const WARDROBE_COLUMNS = [...BASE_COLUMNS, ...MESH_COLUMNS].join(",")
const LEGACY_COLUMNS = BASE_COLUMNS.join(",")

export async function fetchWardrobeItems(
  userId: string,
): Promise<WardrobeItemRow[]> {
  const query = (columns: string) =>
    supabase
      .from("items")
      .select(columns)
      .eq("user_id", userId)
      .order("created_at", { ascending: false })

  let { data, error } = await query(WARDROBE_COLUMNS)
  if (error && /mesh_/i.test(error.message)) {
    // The item-mesh migration has not been applied yet.
    ;({ data, error } = await query(LEGACY_COLUMNS))
  }

  if (error) throw error
  return (data ?? []) as unknown as WardrobeItemRow[]
}
