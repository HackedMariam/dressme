import type { WardrobeItemRow } from "../../lib/database.types"
import { supabase } from "../../lib/supabase"

const WARDROBE_COLUMNS = [
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
].join(",")

export async function fetchWardrobeItems(
  userId: string,
): Promise<WardrobeItemRow[]> {
  const { data, error } = await supabase
    .from("items")
    .select(WARDROBE_COLUMNS)
    .eq("user_id", userId)
    .order("created_at", { ascending: false })

  if (error) throw error
  return (data ?? []) as unknown as WardrobeItemRow[]
}
