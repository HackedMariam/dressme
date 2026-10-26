import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"
import type { ProfileRow, StyleProfileRow } from "../../lib/database.types"
import { useAuth } from "../auth/AuthProvider"
import {
  completeOnboarding as completeOnboardingRequest,
  initializeUserData,
  saveOnboardingDraft as saveOnboardingDraftRequest,
  savePreferences as savePreferencesRequest,
  updateProfile as updateProfileRequest,
} from "./api"
import type { PreferencesUpdate, ProfileUpdate } from "./types"
import { describeError } from "./validation"

interface UserDataContextValue {
  profile: ProfileRow | null
  preferences: StyleProfileRow | null
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  saveProfile: (patch: ProfileUpdate) => Promise<ProfileRow>
  savePreferences: (patch: PreferencesUpdate) => Promise<StyleProfileRow>
  saveOnboardingDraft: (
    profilePatch: ProfileUpdate,
    preferencesPatch: PreferencesUpdate,
    nextStep: number,
  ) => Promise<void>
  completeOnboarding: (
    profilePatch: ProfileUpdate,
    preferencesPatch: PreferencesUpdate,
  ) => Promise<void>
}

const UserDataContext = createContext<UserDataContextValue | null>(null)

export function UserDataProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const [profile, setProfile] = useState<ProfileRow | null>(null)
  const [preferences, setPreferences] = useState<StyleProfileRow | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const requestId = useRef(0)

  const load = useCallback(async () => {
    if (!user) {
      setProfile(null)
      setPreferences(null)
      setLoading(false)
      setError(null)
      return
    }

    const currentRequest = ++requestId.current
    setLoading(true)
    setError(null)

    try {
      const data = await initializeUserData(user)
      if (currentRequest !== requestId.current) return
      setProfile(data.profile)
      setPreferences(data.preferences)
    } catch (loadError) {
      if (currentRequest !== requestId.current) return
      setError(describeError(loadError))
    } finally {
      if (currentRequest === requestId.current) setLoading(false)
    }
  }, [user])

  useEffect(() => {
    void load()
    return () => {
      requestId.current += 1
    }
  }, [load])

  const refresh = useCallback(async () => {
    await load()
  }, [load])

  const saveProfile = useCallback(
    async (patch: ProfileUpdate) => {
      if (!user) throw new Error("You must be signed in to save your profile.")
      const next = await updateProfileRequest(user.id, patch)
      setProfile(next)
      return next
    },
    [user],
  )

  const savePreferences = useCallback(
    async (patch: PreferencesUpdate) => {
      if (!user)
        throw new Error("You must be signed in to save your preferences.")
      const next = await savePreferencesRequest(user.id, patch)
      setPreferences(next)
      return next
    },
    [user],
  )

  const saveOnboardingDraft = useCallback(
    async (
      profilePatch: ProfileUpdate,
      preferencesPatch: PreferencesUpdate,
      nextStep: number,
    ) => {
      if (!user) throw new Error("You must be signed in to save your progress.")
      const data = await saveOnboardingDraftRequest(
        user.id,
        profilePatch,
        preferencesPatch,
        nextStep,
      )
      setProfile(data.profile)
      setPreferences(data.preferences)
    },
    [user],
  )

  const completeOnboarding = useCallback(
    async (
      profilePatch: ProfileUpdate,
      preferencesPatch: PreferencesUpdate,
    ) => {
      if (!user) throw new Error("You must be signed in to finish onboarding.")
      const data = await completeOnboardingRequest(
        user.id,
        profilePatch,
        preferencesPatch,
      )
      setProfile(data.profile)
      setPreferences(data.preferences)
    },
    [user],
  )

  const value = useMemo(
    () => ({
      profile,
      preferences,
      loading,
      error,
      refresh,
      saveProfile,
      savePreferences,
      saveOnboardingDraft,
      completeOnboarding,
    }),
    [
      profile,
      preferences,
      loading,
      error,
      refresh,
      saveProfile,
      savePreferences,
      saveOnboardingDraft,
      completeOnboarding,
    ],
  )

  return (
    <UserDataContext.Provider value={value}>
      {children}
    </UserDataContext.Provider>
  )
}

export function useUserData(): UserDataContextValue {
  const context = useContext(UserDataContext)
  if (!context) {
    throw new Error("useUserData must be used inside UserDataProvider")
  }
  return context
}
