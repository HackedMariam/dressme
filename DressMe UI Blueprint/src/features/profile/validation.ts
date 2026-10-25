import {
  CATEGORY_OPTIONS,
  COLOR_OPTIONS,
  CURRENCY_OPTIONS,
  FIT_OPTIONS,
  LANGUAGE_OPTIONS,
  OCCASION_OPTIONS,
  SIZE_SYSTEM_OPTIONS,
  STYLE_OPTIONS,
  TEMPERATURE_OPTIONS,
} from "./options"
import {
  clothingSizesToJson,
  type PreferencesInput,
  type PreferencesUpdate,
  type ProfileInput,
  type ProfileUpdate,
} from "./types"

const values = (options: { value: string }[]) =>
  options.map((option) => option.value)

const STYLE_VALUES = new Set(values(STYLE_OPTIONS))
const COLOR_VALUES = new Set(values(COLOR_OPTIONS))
const OCCASION_VALUES = new Set(values(OCCASION_OPTIONS))
const CATEGORY_VALUES = new Set(values(CATEGORY_OPTIONS))
const FIT_VALUES = new Set(values(FIT_OPTIONS))
const LANGUAGE_VALUES = new Set(values(LANGUAGE_OPTIONS))
const CURRENCY_VALUES = new Set(values(CURRENCY_OPTIONS))
const TEMPERATURE_VALUES = new Set(values(TEMPERATURE_OPTIONS))
const SIZE_SYSTEM_VALUES = new Set(values(SIZE_SYSTEM_OPTIONS))

export class ValidationError extends Error {
  field?: string

  constructor(message: string, field?: string) {
    super(message)
    this.name = "ValidationError"
    this.field = field
  }
}

function requireOneOf(
  value: string,
  allowed: Set<string>,
  label: string,
): string {
  const trimmed = value.trim()
  if (!allowed.has(trimmed)) {
    throw new ValidationError(`Choose a valid ${label}.`)
  }
  return trimmed
}

function cleanText(value: string, label: string, maxLength = 80): string {
  const trimmed = value.trim()
  if (trimmed.length > maxLength) {
    throw new ValidationError(
      `${label} must be ${maxLength} characters or fewer.`,
    )
  }
  return trimmed
}

function cleanMultiSelect(
  selected: string[],
  allowed: Set<string>,
  label: string,
): string[] {
  const unique = Array.from(
    new Set(selected.map((value) => value.trim()).filter(Boolean)),
  )

  if (unique.length > 30) {
    throw new ValidationError(`Select at most 30 ${label}.`)
  }

  for (const value of unique) {
    if (!allowed.has(value)) {
      throw new ValidationError(`"${value}" is not a valid ${label} option.`)
    }
  }

  return unique
}

export function validateEmail(email: string): string {
  const trimmed = email.trim().toLowerCase()
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
    throw new ValidationError("Enter a valid email address.")
  }
  return trimmed
}

export function validatePassword(password: string): string {
  if (password.length < 8) {
    throw new ValidationError("Password must be at least 8 characters.")
  }
  return password
}

export function validateDisplayName(name: string, required: boolean): string {
  const trimmed = cleanText(name, "Display name")

  if (required && !trimmed) {
    throw new ValidationError("Please enter your name.")
  }

  return trimmed
}

export function validateOnboardingStep(step: number): number {
  if (!Number.isInteger(step) || step < 0 || step > 10) {
    throw new ValidationError("Invalid onboarding step.")
  }
  return step
}

export function validateProfileInput(
  input: ProfileInput,
  options: { requireDisplayName?: boolean } = {},
): ProfileUpdate {
  const displayName = validateDisplayName(
    input.display_name,
    Boolean(options.requireDisplayName),
  )
  const country = cleanText(input.country, "Country")
  const city = cleanText(input.city, "City")

  if (!LANGUAGE_VALUES.has(input.preferred_language)) {
    throw new ValidationError("Choose a supported language.")
  }

  return {
    display_name: displayName,
    preferred_language: input.preferred_language,
    location: country || city ? { country, city } : null,
    default_currency: requireOneOf(
      input.default_currency,
      CURRENCY_VALUES,
      "currency",
    ),
    temperature_unit: requireOneOf(
      input.temperature_unit,
      TEMPERATURE_VALUES,
      "temperature unit",
    ),
    size_system: requireOneOf(
      input.size_system,
      SIZE_SYSTEM_VALUES,
      "size system",
    ),
    notifications_enabled: Boolean(input.notifications_enabled),
    weather_sync_enabled: Boolean(input.weather_sync_enabled),
    ai_style_tips_enabled: Boolean(input.ai_style_tips_enabled),
  }
}

export function validatePreferencesInput(
  input: PreferencesInput,
): PreferencesUpdate {
  const preferredFit = input.preferred_fit.trim()

  if (preferredFit && !FIT_VALUES.has(preferredFit)) {
    throw new ValidationError("Choose a valid fit preference.")
  }

  return {
    preferred_styles: cleanMultiSelect(
      input.preferred_styles,
      STYLE_VALUES,
      "style",
    ),
    preferred_colors: cleanMultiSelect(
      input.preferred_colors,
      COLOR_VALUES,
      "colour",
    ),
    avoided_colors: cleanMultiSelect(
      input.avoided_colors,
      COLOR_VALUES,
      "colour",
    ),
    preferred_occasions: cleanMultiSelect(
      input.preferred_occasions,
      OCCASION_VALUES,
      "occasion",
    ),
    preferred_categories: cleanMultiSelect(
      input.preferred_categories,
      CATEGORY_VALUES,
      "category",
    ),
    preferred_fit: preferredFit || null,
    clothing_sizes: clothingSizesToJson(input.clothing_sizes),
  }
}

export function describeError(error: unknown): string {
  if (error instanceof ValidationError) return error.message

  if (!error || typeof error !== "object") {
    return "Something went wrong. Please try again."
  }

  const candidate = error as {
    code?: string
    message?: string
    status?: number
    name?: string
  }

  const code = candidate.code ?? ""
  const message = candidate.message ?? ""

  if (
    candidate.status === 401 ||
    /jwt expired|session.*expired|refresh token/i.test(message)
  ) {
    return "Your session has expired. Please sign in again."
  }

  if (code === "42501" || candidate.status === 403) {
    return "You do not have permission to change this information."
  }

  if (code === "23514") {
    return "One of the values is not accepted. Check the highlighted fields and try again."
  }

  if (code === "23503") {
    return "Your account session is no longer valid. Please sign in again."
  }

  if (code === "23505" || candidate.status === 409) {
    return "That record already exists."
  }

  if (code === "PGRST116") {
    return "We could not find your profile. Try reloading the page."
  }

  if (code === "PGRST202" || code === "PGRST205") {
    return "The database is not fully set up. Apply the latest Supabase migration and try again."
  }

  if (/invalid login credentials/i.test(message)) {
    return "Email or password is incorrect."
  }

  if (/email not confirmed/i.test(message)) {
    return "Please confirm your email address before signing in."
  }

  if (/failed to fetch|network ?error|load failed/i.test(message)) {
    return "Network error. Check your connection and try again."
  }

  if (message) return message

  return "Something went wrong. Please try again."
}
