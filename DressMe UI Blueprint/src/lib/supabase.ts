import { createClient } from "@supabase/supabase-js"
import type { Database } from "./database.types"

const supabaseUrl =
  import.meta.env.SUPABASE_URL?.trim() || import.meta.env.VITE_SUPABASE_URL?.trim()
const supabaseAnonKey =
  import.meta.env.SUPABASE_ANON_KEY?.trim() ||
  import.meta.env.VITE_SUPABASE_ANON_KEY?.trim()

export const isSupabaseConfigured = Boolean(supabaseUrl && supabaseAnonKey)

// The fallback values let the module import safely so the UI can show a clear
// configuration message instead of crashing before React renders.
export const supabase = createClient<Database>(
  supabaseUrl || "http://localhost:54321",
  supabaseAnonKey || "missing-supabase-anon-key",
  {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
    },
  },
)

export function getSupabaseConfigMessage(): string | null {
  if (isSupabaseConfigured) return null
  return "Supabase is not configured. Add SUPABASE_URL and SUPABASE_ANON_KEY to the frontend environment. Do not use the service-role key in the browser."
}
