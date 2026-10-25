import { beforeEach, describe, expect, it, vi } from "vitest"
import type { User } from "@supabase/supabase-js"

const mocks = vi.hoisted(() => ({
  from: vi.fn(),
  rpc: vi.fn(),
}))

vi.mock("../../lib/supabase", () => ({
  supabase: {
    from: mocks.from,
    rpc: mocks.rpc,
  },
}))

import {
  completeOnboarding,
  initializeUserData,
  saveOnboardingDraft,
} from "./api"
import type { ProfileRow, StyleProfileRow } from "../../lib/database.types"

const profile: ProfileRow = {
  id: "user-1",
  display_name: "Sophia",
  default_currency: "EUR",
  timezone: "UTC",
  location: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  preferred_language: "en",
  avatar_url: null,
  onboarding_completed: false,
  onboarding_step: 0,
  temperature_unit: "Celsius",
  size_system: "EU",
  notifications_enabled: true,
  weather_sync_enabled: true,
  ai_style_tips_enabled: false,
}

const preferences: StyleProfileRow = {
  user_id: "user-1",
  preferred_styles: [],
  preferred_colors: [],
  avoided_colors: [],
  preferred_fit: null,
  clothing_sizes: [],
  updated_at: "2026-01-01T00:00:00Z",
  preferred_occasions: [],
  preferred_categories: [],
}

function updateChain(result: { data: ProfileRow | null; error: unknown }) {
  const single = vi.fn().mockResolvedValue(result)
  const select = vi.fn().mockReturnValue({ single })
  const eq = vi.fn().mockReturnValue({ select })
  const update = vi.fn().mockReturnValue({ eq })
  return { update, eq, select, single }
}

function upsertChain(result: { data: StyleProfileRow | null; error: unknown }) {
  const single = vi.fn().mockResolvedValue(result)
  const select = vi.fn().mockReturnValue({ single })
  const upsert = vi.fn().mockReturnValue({ select })
  return { upsert, select, single }
}

function selectChain(result: { data: unknown; error: unknown }) {
  const maybeSingle = vi.fn().mockResolvedValue(result)
  const eq = vi.fn().mockReturnValue({ maybeSingle })
  const select = vi.fn().mockReturnValue({ eq })
  return { select, eq, maybeSingle }
}

describe("profile persistence", () => {
  beforeEach(() => {
    mocks.from.mockReset()
    mocks.rpc.mockReset()
  })

  it("does not recreate an existing profile", async () => {
    const profileRead = selectChain({ data: profile, error: null })
    const preferencesRead = selectChain({ data: preferences, error: null })

    mocks.from.mockImplementation((table: string) =>
      table === "profiles" ? profileRead : preferencesRead,
    )

    const user = {
      id: "user-1",
      user_metadata: { full_name: "Sophia" },
    } as unknown as User
    const data = await initializeUserData(user)

    expect(data.profile).toBe(profile)
    expect(data.preferences).toBe(preferences)
    expect(mocks.rpc).not.toHaveBeenCalled()
  })

  it("saves preferences before marking onboarding complete", async () => {
    const styleChain = upsertChain({ data: preferences, error: null })
    const profileChain = updateChain({
      data: { ...profile, onboarding_completed: true },
      error: null,
    })

    mocks.from.mockImplementation((table: string) =>
      table === "style_profiles" ? styleChain : profileChain,
    )

    await completeOnboarding(
      "user-1",
      { display_name: "Sophia", onboarding_step: 0 },
      { preferred_styles: ["Minimalist"] },
    )

    expect(mocks.from.mock.calls.map((call) => call[0])).toEqual([
      "style_profiles",
      "profiles",
    ])
    expect(profileChain.update).toHaveBeenCalledWith(
      expect.objectContaining({
        display_name: "Sophia",
        onboarding_completed: true,
        onboarding_step: 2,
      }),
    )
  })

  it("does not mark onboarding complete when preferences fail", async () => {
    const failure = { code: "23514", message: "constraint failed" }
    const styleChain = upsertChain({ data: null, error: failure })
    const profileChain = updateChain({ data: profile, error: null })

    mocks.from.mockImplementation((table: string) =>
      table === "style_profiles" ? styleChain : profileChain,
    )

    await expect(
      completeOnboarding("user-1", { display_name: "Sophia" }, {}),
    ).rejects.toEqual(failure)

    expect(profileChain.update).not.toHaveBeenCalled()
  })

  it("keeps onboarding incomplete when saving a draft", async () => {
    const styleChain = upsertChain({ data: preferences, error: null })
    const profileChain = updateChain({
      data: { ...profile, onboarding_step: 1 },
      error: null,
    })

    mocks.from.mockImplementation((table: string) =>
      table === "style_profiles" ? styleChain : profileChain,
    )

    await saveOnboardingDraft(
      "user-1",
      { display_name: "Sophia" },
      { preferred_styles: ["Minimalist"] },
      1,
    )

    expect(profileChain.update).toHaveBeenCalledWith(
      expect.objectContaining({
        onboarding_completed: false,
        onboarding_step: 1,
      }),
    )
  })
})
