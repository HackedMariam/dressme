export type Json = string | number | boolean | null | {
  [key: string]: Json | undefined
} | Json[]

export type ProfileRow = {
  id: string
  display_name: string
  default_currency: string
  timezone: string
  location: Json | null
  created_at: string
  updated_at: string
  preferred_language: string | null
  avatar_url: string | null
  onboarding_completed: boolean
  onboarding_step: number
  temperature_unit: string
  size_system: string
  notifications_enabled: boolean
  weather_sync_enabled: boolean
  ai_style_tips_enabled: boolean
}

export type StyleProfileRow = {
  user_id: string
  preferred_styles: string[]
  preferred_colors: string[]
  avoided_colors: string[]
  preferred_fit: string | null
  clothing_sizes: Json
  updated_at: string
  preferred_occasions: string[]
  preferred_categories: string[]
}

export type WardrobeItemRow = {
  id: string
  user_id: string | null
  name: string
  category: string
  category_group: string
  subcategory: string | null
  color_name: string | null
  color_hex: string | null
  color_family: string | null
  colors: Json | null
  pattern: string | null
  material: string | null
  seasons: string[] | null
  style: string | null
  occasions: string[] | null
  formality: number | null
  warmth: number | null
  description: string | null
  styling_tips: string[] | null
  tags: string[] | null
  confidence: number | null
  field_confidence: Json | null
  needs_review: boolean
  status: string
  image_url: string | null
  cutout_url: string | null
  zone: string | null
  position_3d: Json | null
  detection: Json | null
  predicted: Json | null
  enrichment_source: string | null
  created_at: string
}

export type UserAvatarRow = {
  user_id: string
  targets: Json
  details: Json
  outfit: Json
  metrics: Json
  glb_path: string
  glb_bytes: number | null
  generated_at: string
  updated_at: string
}

type ProfileInsert = {
  id: string
  display_name?: string
  default_currency?: string
  timezone?: string
  location?: Json | null
  created_at?: string
  updated_at?: string
  preferred_language?: string | null
  avatar_url?: string | null
  onboarding_completed?: boolean
  onboarding_step?: number
  temperature_unit?: string
  size_system?: string
  notifications_enabled?: boolean
  weather_sync_enabled?: boolean
  ai_style_tips_enabled?: boolean
}

type ProfileUpdate = Partial<Omit<ProfileInsert, "id">>

type StyleProfileInsert = {
  user_id: string
  preferred_styles?: string[]
  preferred_colors?: string[]
  avoided_colors?: string[]
  preferred_fit?: string | null
  clothing_sizes?: Json
  updated_at?: string
  preferred_occasions?: string[]
  preferred_categories?: string[]
}

type StyleProfileUpdate = Partial<Omit<StyleProfileInsert, "user_id">>

export interface Database {
  public: {
    Tables: {
      profiles: {
        Row: ProfileRow
        Insert: ProfileInsert
        Update: ProfileUpdate
        Relationships: []
      }
      style_profiles: {
        Row: StyleProfileRow
        Insert: StyleProfileInsert
        Update: StyleProfileUpdate
        Relationships: []
      }
      items: {
        Row: WardrobeItemRow
        Insert: Partial<WardrobeItemRow>
        Update: Partial<WardrobeItemRow>
        Relationships: []
      }
      user_avatars: {
        Row: UserAvatarRow
        Insert: Partial<UserAvatarRow> & { user_id: string; glb_path: string }
        Update: Partial<UserAvatarRow>
        Relationships: []
      }
    }
    Views: { [_ in never]: never }
    Functions: {
      ensure_user_profile: {
        Args: Record<string, never>
        Returns: ProfileRow
      }
    }
    Enums: { [_ in never]: never }
    CompositeTypes: { [_ in never]: never }
  }
}
