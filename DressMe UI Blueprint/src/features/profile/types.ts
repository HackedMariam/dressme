import type {
  Json,
  ProfileRow,
  StyleProfileRow,
} from "../../lib/database.types"
import type { ClothingSizeKey } from "./options"

export type ProfileUpdate = {
  display_name?: string
  preferred_language?: string | null
  default_currency?: string
  timezone?: string
  location?: Json | null
  avatar_url?: string | null
  onboarding_completed?: boolean
  onboarding_step?: number
  temperature_unit?: string
  size_system?: string
  notifications_enabled?: boolean
  weather_sync_enabled?: boolean
  ai_style_tips_enabled?: boolean
}

export type PreferencesUpdate = {
  preferred_styles?: string[]
  preferred_colors?: string[]
  avoided_colors?: string[]
  preferred_occasions?: string[]
  preferred_categories?: string[]
  preferred_fit?: string | null
  clothing_sizes?: Json
}

export interface ProfileInput {
  display_name: string
  preferred_language: string
  country: string
  city: string
  default_currency: string
  temperature_unit: string
  size_system: string
  notifications_enabled: boolean
  weather_sync_enabled: boolean
  ai_style_tips_enabled: boolean
}

export type ClothingSizes = Record<ClothingSizeKey, string>

export interface PreferencesInput {
  preferred_styles: string[]
  preferred_colors: string[]
  avoided_colors: string[]
  preferred_occasions: string[]
  preferred_categories: string[]
  preferred_fit: string
  clothing_sizes: ClothingSizes
}

export const EMPTY_SIZES: ClothingSizes = {
  top: "",
  bottom: "",
  dress: "",
  shoes: "",
}

export function parseLocation(
  value: Json | null,
): { country: string; city: string } {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return { country: "", city: "" }
  }

  const country = typeof value.country === "string" ? value.country : ""
  const city = typeof value.city === "string" ? value.city : ""

  return { country, city }
}

export function normalizeClothingSizes(value: Json | null): ClothingSizes {
  const sizes: ClothingSizes = { ...EMPTY_SIZES }

  if (Array.isArray(value)) {
    for (const entry of value) {
      if (!entry || typeof entry !== "object" || Array.isArray(entry)) continue
      const key = entry.key
      const sizeValue = entry.value
      if (
        typeof key === "string" &&
        key in sizes &&
        typeof sizeValue === "string"
      ) {
        sizes[(key as ClothingSizeKey)] = sizeValue
      }
    }
    return sizes
  }

  if (value && typeof value === "object") {
    for (const key of Object.keys(sizes) as ClothingSizeKey[]) {
      const sizeValue = value[key]
      if (typeof sizeValue === "string") sizes[key] = sizeValue
    }
  }

  return sizes
}

export function clothingSizesToJson(sizes: ClothingSizes): Json {
  return (Object.keys(sizes) as ClothingSizeKey[])
    .map((key) => ({ key, value: sizes[key].trim() }))
    .filter((entry) => entry.value.length > 0)
}

export function profileToInput(profile: ProfileRow | null): ProfileInput {
  const location = parseLocation(profile?.location ?? null)

  return {
    display_name: profile?.display_name ?? "",
    preferred_language: profile?.preferred_language ?? "en",
    country: location.country,
    city: location.city,
    default_currency: profile?.default_currency ?? "EUR",
    temperature_unit: profile?.temperature_unit ?? "Celsius",
    size_system: profile?.size_system ?? "EU",
    notifications_enabled: profile?.notifications_enabled ?? true,
    weather_sync_enabled: profile?.weather_sync_enabled ?? true,
    ai_style_tips_enabled: profile?.ai_style_tips_enabled ?? false,
  }
}

export function preferencesToInput(
  preferences: StyleProfileRow | null,
): PreferencesInput {
  return {
    preferred_styles: preferences?.preferred_styles ?? [],
    preferred_colors: preferences?.preferred_colors ?? [],
    avoided_colors: preferences?.avoided_colors ?? [],
    preferred_occasions: preferences?.preferred_occasions ?? [],
    preferred_categories: preferences?.preferred_categories ?? [],
    preferred_fit: preferences?.preferred_fit ?? "",
    clothing_sizes: normalizeClothingSizes(preferences?.clothing_sizes ?? null),
  }
}

export function firstName(displayName: string | null | undefined): string {
  const trimmed = (displayName ?? "").trim()
  if (!trimmed) return "there"
  return trimmed.split(/\s+/)[0]
}

export function userInitial(
  displayName: string | null | undefined,
  email: string | null | undefined,
): string {
  const source = (displayName ?? "").trim() || (email ?? "").trim()
  return source ? source[0].toUpperCase() : "D"
}
