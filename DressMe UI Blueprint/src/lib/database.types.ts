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
