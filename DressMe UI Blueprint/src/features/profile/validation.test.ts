import { describe, expect, it } from "vitest"
import {
  describeError,
  validateEmail,
  validatePassword,
  validatePreferencesInput,
  validateProfileInput,
} from "./validation"
import {
  clothingSizesToJson,
  normalizeClothingSizes,
  parseLocation,
  preferencesToInput,
  profileToInput,
} from "./types"
import type { ProfileRow, StyleProfileRow } from "../../lib/database.types"

const profile: ProfileRow = {
  id: "user-1",
  display_name: "Sophia Laurent",
  default_currency: "EUR",
  timezone: "UTC",
  location: { country: "Tunisia", city: "Tunis" },
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  preferred_language: "fr",
  avatar_url: null,
  onboarding_completed: false,
  onboarding_step: 1,
  temperature_unit: "Celsius",
  size_system: "EU",
  notifications_enabled: true,
  weather_sync_enabled: true,
  ai_style_tips_enabled: false,
}

const preferences: StyleProfileRow = {
  user_id: "user-1",
  preferred_styles: ["Minimalist"],
  preferred_colors: ["Ivory"],
  avoided_colors: [],
  preferred_fit: "regular",
  clothing_sizes: [
    { key: "top", value: "S" },
    { key: "shoes", value: "EU 38" },
  ],
  updated_at: "2026-01-01T00:00:00Z",
  preferred_occasions: ["Work / Office"],
  preferred_categories: ["Tops"],
}

describe("profile form conversion", () => {
  it("loads saved profile fields and location", () => {
    const input = profileToInput(profile)

    expect(input.display_name).toBe("Sophia Laurent")
    expect(input.preferred_language).toBe("fr")
    expect(input.country).toBe("Tunisia")
    expect(input.city).toBe("Tunis")
    expect(input.notifications_enabled).toBe(true)
  })

  it("handles missing profiles and legacy clothing size arrays", () => {
    expect(profileToInput(null)).toMatchObject({
      display_name: "",
      preferred_language: "en",
      country: "",
      city: "",
    })

    expect(normalizeClothingSizes([])).toEqual({
      top: "",
      bottom: "",
      dress: "",
      shoes: "",
    })

    expect(
      normalizeClothingSizes({
        top: "M",
        bottom: "L",
      }),
    ).toMatchObject({ top: "M", bottom: "L", dress: "", shoes: "" })
  })

  it("serialises sizes as the JSON array required by the schema", () => {
    expect(
      clothingSizesToJson({
        top: " S ",
        bottom: "",
        dress: "XS-S",
        shoes: " EU 38 ",
      }),
    ).toEqual([
      { key: "top", value: "S" },
      { key: "dress", value: "XS-S" },
      { key: "shoes", value: "EU 38" },
    ])
  })

  it("parses partial locations safely", () => {
    expect(parseLocation(null)).toEqual({ country: "", city: "" })
    expect(parseLocation(["not", "an", "object"])).toEqual({
      country: "",
      city: "",
    })
    expect(parseLocation({ city: "Tunis" })).toEqual({
      country: "",
      city: "Tunis",
    })
  })
})

describe("profile validation", () => {
  it("trims values and builds a location object", () => {
    const patch = validateProfileInput(profileToInput(profile), {
      requireDisplayName: true,
    })

    expect(patch.display_name).toBe("Sophia Laurent")
    expect(patch.location).toEqual({ country: "Tunisia", city: "Tunis" })
    expect(patch.default_currency).toBe("EUR")
  })

  it("stores null when country and city are empty", () => {
    const patch = validateProfileInput({
      ...profileToInput(profile),
      country: "",
      city: "",
    })

    expect(patch.location).toBeNull()
  })

  it("requires a name for onboarding and rejects invalid options", () => {
    expect(() =>
      validateProfileInput(
        { ...profileToInput(profile), display_name: "   " },
        { requireDisplayName: true },
      ),
    ).toThrow("Please enter your name.")

    expect(() =>
      validateProfileInput({
        ...profileToInput(profile),
        preferred_language: "de",
      }),
    ).toThrow("Choose a supported language.")

    expect(() =>
      validateProfileInput({
        ...profileToInput(profile),
        default_currency: "BTC",
      }),
    ).toThrow("Choose a valid currency.")
  })
})

describe("preference validation", () => {
  it("deduplicates selections and serialises sizes", () => {
    const input = preferencesToInput(preferences)
    const patch = validatePreferencesInput({
      ...input,
      preferred_styles: [...input.preferred_styles, "Minimalist"],
    })

    expect(patch.preferred_styles).toEqual(["Minimalist"])
    expect(patch.preferred_fit).toBe("regular")
    expect(patch.clothing_sizes).toEqual([
      { key: "top", value: "S" },
      { key: "shoes", value: "EU 38" },
    ])
  })

  it("accepts an empty fit preference as null", () => {
    const patch = validatePreferencesInput({
      ...preferencesToInput(preferences),
      preferred_fit: "",
    })

    expect(patch.preferred_fit).toBeNull()
  })

  it("rejects values outside the allowed options", () => {
    expect(() =>
      validatePreferencesInput({
        ...preferencesToInput(preferences),
        preferred_colors: ["Neon"],
      }),
    ).toThrow('"Neon" is not a valid colour option.')

    expect(() =>
      validatePreferencesInput({
        ...preferencesToInput(preferences),
        preferred_fit: "oversized",
      }),
    ).toThrow("Choose a valid fit preference.")
  })
})

describe("auth validation", () => {
  it("normalises email and enforces password length", () => {
    expect(validateEmail("  SOPHIA@Example.com ")).toBe("sophia@example.com")
    expect(() => validateEmail("not-an-email")).toThrow(
      "Enter a valid email address.",
    )
    expect(() => validatePassword("short")).toThrow(
      "Password must be at least 8 characters.",
    )
  })
})

describe("error messages", () => {
  it("maps session, permission, constraint and network failures", () => {
    expect(describeError({ status: 401, message: "expired" })).toBe(
      "Your session has expired. Please sign in again.",
    )
    expect(describeError({ code: "42501", message: "denied" })).toBe(
      "You do not have permission to change this information.",
    )
    expect(describeError({ code: "23514", message: "check" })).toContain(
      "One of the values is not accepted",
    )
    expect(describeError({ message: "Failed to fetch" })).toBe(
      "Network error. Check your connection and try again.",
    )
    expect(describeError(new Error("boom"))).toBe("boom")
  })
})
