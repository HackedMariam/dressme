import type { BodyTargets, DetailTargets } from "./avatarApi"
import type { TryOnItemSnapshot } from "./tryon"
import { supabase } from "./supabase"

export type SavedAvatarProfile = {
  targets: BodyTargets
  details: DetailTargets
  appearance: Record<string, string>
  wardrobe: TryOnItemSnapshot[]
  heightCm: number
  source: "photos" | "manual"
  confidence: number
}

function jsonObject(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

export async function loadAvatarProfile(userId: string): Promise<SavedAvatarProfile | null> {
  const { data, error } = await supabase
    .from("avatar_profiles")
    .select("targets,details,appearance,wardrobe,height_cm,source,confidence")
    .eq("user_id", userId)
    .maybeSingle()
  if (error) throw error
  if (!data) return null
  const row = data as {
    targets: unknown
    details: unknown
    appearance: unknown
    wardrobe: unknown
    height_cm: number
    source: string
    confidence: number
  }
  return {
    targets: jsonObject(row.targets) as BodyTargets,
    details: jsonObject(row.details) as DetailTargets,
    appearance: jsonObject(row.appearance) as Record<string, string>,
    wardrobe: Array.isArray(row.wardrobe) ? row.wardrobe as TryOnItemSnapshot[] : [],
    heightCm: row.height_cm,
    source: row.source === "photos" ? "photos" : "manual",
    confidence: Number(row.confidence) || 0,
  }
}

export async function saveAvatarProfile(
  userId: string,
  profile: SavedAvatarProfile,
): Promise<void> {
  const { error } = await supabase.from("avatar_profiles").upsert({
    user_id: userId,
    targets: profile.targets,
    details: profile.details,
    appearance: profile.appearance,
    wardrobe: profile.wardrobe,
    height_cm: profile.heightCm,
    source: profile.source,
    confidence: profile.confidence,
    updated_at: new Date().toISOString(),
  })
  if (error) throw error
}
