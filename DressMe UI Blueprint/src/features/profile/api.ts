import type { User } from "@supabase/supabase-js"
import type { ProfileRow, StyleProfileRow } from "../../lib/database.types"
import { supabase } from "../../lib/supabase"
import { MAX_ONBOARDING_STEP } from "./options"
import type { PreferencesUpdate, ProfileUpdate } from "./types"

export interface UserData {
  profile: ProfileRow
  preferences: StyleProfileRow
}

function metadataName(user: User): string {
  const metadata = (user.user_metadata ?? {}) as Record<string, unknown>
  const name = metadata.full_name ?? metadata.name
  return typeof name === "string" ? name.trim() : ""
}

export async function fetchProfile(userId: string): Promise<ProfileRow | null> {
  const { data, error } = await supabase
    .from("profiles")
    .select("*")
    .eq("id", userId)
    .maybeSingle()

  if (error) throw error
  return data
}

export async function fetchPreferences(
  userId: string,
): Promise<StyleProfileRow | null> {
  const { data, error } = await supabase
    .from("style_profiles")
    .select("*")
    .eq("user_id", userId)
    .maybeSingle()

  if (error) throw error
  return data
}

async function insertProfile(user: User): Promise<ProfileRow> {
  const { data, error } = await supabase
    .from("profiles")
    .insert({
      id: user.id,
      display_name: metadataName(user),
    })
    .select("*")
    .single()

  if (error) {
    // Another tab (or React StrictMode) may have created the row first. Do not
    // overwrite it, just return the existing profile.
    if (error.code === "23505") {
      const existing = await fetchProfile(user.id)
      if (existing) return existing
    }
    throw error
  }

  return data
}

async function insertPreferences(userId: string): Promise<StyleProfileRow> {
  const { data, error } = await supabase
    .from("style_profiles")
    .upsert({ user_id: userId }, { onConflict: "user_id" })
    .select("*")
    .single()

  if (error) throw error
  return data
}

/**
 * Loads the authenticated user's profile/preferences and creates either row
 * when it is missing. Safe to call repeatedly.
 */
export async function initializeUserData(user: User): Promise<UserData> {
  let profile = await fetchProfile(user.id)

  if (!profile) {
    const { data, error } = await supabase.rpc("ensure_user_profile")

    if (error) {
      // The RPC is added by the profile migration. Fall back to a normal
      // insert so environments that have not applied it still work as long as
      // the table policies allow the operation.
      if (error.code === "PGRST202" || error.code === "PGRST205") {
        profile = await insertProfile(user)
      } else {
        throw error
      }
    } else {
      profile = data
    }
  }

  let preferences = await fetchPreferences(user.id)

  if (!preferences) {
    preferences = await insertPreferences(user.id)
  }

  // The auth trigger creates the profile before onboarding. If it could not
  // read the full name from signup metadata, seed it once from the auth user
  // so the user does not have to type it again. Only do this for untouched
  // rows, so a name the user later clears is not silently restored.
  if (
    profile &&
    !profile.display_name.trim() &&
    profile.created_at === profile.updated_at
  ) {
    const signupName = metadataName(user)
    if (signupName) {
      profile = await updateProfile(user.id, { display_name: signupName })
    }
  }

  return { profile, preferences }
}

export async function updateProfile(
  userId: string,
  patch: ProfileUpdate,
): Promise<ProfileRow> {
  const { data, error } = await supabase
    .from("profiles")
    .update(patch)
    .eq("id", userId)
    .select("*")
    .single()

  if (error) throw error
  return data
}

export async function savePreferences(
  userId: string,
  patch: PreferencesUpdate,
): Promise<StyleProfileRow> {
  const { data, error } = await supabase
    .from("style_profiles")
    .upsert({ user_id: userId, ...patch }, { onConflict: "user_id" })
    .select("*")
    .single()

  if (error) throw error
  return data
}

/**
 * Saves a partially completed onboarding step. The completion flag is never
 * touched here, so leaving halfway through keeps onboarding incomplete.
 */
export async function saveOnboardingDraft(
  userId: string,
  profilePatch: ProfileUpdate,
  preferencesPatch: PreferencesUpdate,
  nextStep: number,
): Promise<UserData> {
  const preferences = await savePreferences(userId, preferencesPatch)
  const profile = await updateProfile(userId, {
    ...profilePatch,
    onboarding_step: Math.max(0, Math.min(nextStep, MAX_ONBOARDING_STEP)),
    onboarding_completed: false,
  })

  return { profile, preferences }
}

/**
 * Preferences are persisted first. If they fail, onboarding is not marked as
 * complete. If the profile update fails afterwards, the user remains in
 * onboarding and can retry.
 */
export async function completeOnboarding(
  userId: string,
  profilePatch: ProfileUpdate,
  preferencesPatch: PreferencesUpdate,
): Promise<UserData> {
  const preferences = await savePreferences(userId, preferencesPatch)
  const profile = await updateProfile(userId, {
    ...profilePatch,
    onboarding_step: MAX_ONBOARDING_STEP,
    onboarding_completed: true,
  })

  return { profile, preferences }
}

export async function resetOnboarding(userId: string): Promise<ProfileRow> {
  return updateProfile(userId, {
    onboarding_completed: false,
    onboarding_step: 0,
  })
}
