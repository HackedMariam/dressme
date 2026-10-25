import { useEffect, useMemo, useState } from "react"
import {
  Alert,
  ColorMultiSelect,
  Field,
  MultiSelectChips,
  SegmentedChoice,
  SelectInput,
  Spinner,
  TextInput,
} from "../profile/FormControls"
import {
  CATEGORY_OPTIONS,
  CLOTHING_SIZE_FIELDS,
  COLOR_OPTIONS,
  COUNTRY_OPTIONS,
  FIT_OPTIONS,
  LANGUAGE_OPTIONS,
  MAX_ONBOARDING_STEP,
  OCCASION_OPTIONS,
  ONBOARDING_STEPS,
  SIZE_SYSTEM_OPTIONS,
  STYLE_OPTIONS,
} from "../profile/options"
import {
  profileToInput,
  preferencesToInput,
  type PreferencesInput,
  type ProfileInput,
} from "../profile/types"
import { useUserData } from "../profile/UserDataProvider"
import {
  describeError,
  validatePreferencesInput,
  validateProfileInput,
} from "../profile/validation"

export default function Onboarding({
  onComplete,
  onSkip,
}: {
  onComplete: () => void
  onSkip: () => void
}) {
  const { profile, preferences, saveOnboardingDraft, completeOnboarding } =
    useUserData()
  const [step, setStep] = useState(() =>
    Math.max(0, Math.min(profile?.onboarding_step ?? 0, MAX_ONBOARDING_STEP)),
  )
  const [profileForm, setProfileForm] = useState<ProfileInput>(() =>
    profileToInput(profile),
  )
  const [preferencesForm, setPreferencesForm] = useState<PreferencesInput>(() =>
    preferencesToInput(preferences),
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!profile) return
    setProfileForm((current) =>
      current.display_name || profile.display_name
        ? current
        : { ...current, display_name: profile.display_name },
    )
  }, [profile])

  const isLastStep = step === MAX_ONBOARDING_STEP
  const currentStep = ONBOARDING_STEPS[step]
  const progress = ((step + 1) / ONBOARDING_STEPS.length) * 100

  const countryOptions = useMemo(
    () => [{ value: "", label: "Select a country" }, ...COUNTRY_OPTIONS],
    [],
  )
  const fitOptions = useMemo(
    () => [{ value: "", label: "No preference" }, ...FIT_OPTIONS],
    [],
  )

  const updateProfile = <K extends keyof ProfileInput,>(
    key: K,
    value: ProfileInput[K],
  ) => {
    setProfileForm((current) => ({ ...current, [key]: value }))
  }

  const updatePreferences = <K extends keyof PreferencesInput,>(
    key: K,
    value: PreferencesInput[K],
  ) => {
    setPreferencesForm((current) => ({ ...current, [key]: value }))
  }

  const updateSize = (
    key: keyof PreferencesInput["clothing_sizes"],
    value: string,
  ) => {
    setPreferencesForm((current) => ({
      ...current,
      clothing_sizes: { ...current.clothing_sizes, [key]: value },
    }))
  }

  const next = async () => {
    if (saving) return
    setError(null)

    try {
      const profilePatch = validateProfileInput(profileForm, {
        requireDisplayName: step === 0 || isLastStep,
      })
      const preferencesPatch = validatePreferencesInput(preferencesForm)

      setSaving(true)

      if (isLastStep) {
        await completeOnboarding(profilePatch, preferencesPatch)
        onComplete()
      } else {
        await saveOnboardingDraft(profilePatch, preferencesPatch, step + 1)
        setStep((current) => Math.min(current + 1, MAX_ONBOARDING_STEP))
      }
    } catch (saveError) {
      setError(describeError(saveError))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#FAF9F6]">
      <header className="border-b border-[#E2E0D8] px-6 py-5 sm:px-10">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div className="flex items-baseline gap-1">
            <span className="font-display text-2xl font-semibold italic text-[#1C1C1C]">
              Dress
            </span>
            <span className="font-display text-2xl font-semibold text-[#556B2F]">
              Me
            </span>
          </div>
          <button
            type="button"
            onClick={onSkip}
            disabled={saving}
            className="text-xs font-medium text-[#8C8A82] transition-colors hover:text-[#1C1C1C] disabled:opacity-50"
          >
            Skip for now
          </button>
        </div>
      </header>

      <main className="mx-auto grid max-w-5xl gap-8 px-6 py-10 sm:px-10 lg:grid-cols-[240px_1fr]">
        <aside>
          <p className="text-[11px] font-semibold uppercase tracking-widest text-[#8C8A82]">
            Profile setup
          </p>
          <div className="mt-4 h-1 overflow-hidden rounded-full bg-[#E2E0D8]">
            <div
              className="h-full rounded-full bg-[#556B2F] transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>

          <ol className="mt-6 space-y-3">
            {ONBOARDING_STEPS.map((item, index) => {
              const active = index === step
              const done = index < step
              return (
                <li key={item.title} className="flex items-start gap-3">
                  <span
                    className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${
                      active
                        ? "bg-[#556B2F] text-white"
                        : done
                          ? "bg-[#E8EDE0] text-[#556B2F]"
                          : "bg-[#E2E0D8] text-[#8C8A82]"
                    }`}
                  >
                    {done ? "✓" : index + 1}
                  </span>
                  <div>
                    <p
                      className={`text-sm font-medium ${
                        active ? "text-[#1C1C1C]" : "text-[#8C8A82]"
                      }`}
                    >
                      {item.title}
                    </p>
                    <p className="text-[11px] leading-snug text-[#8C8A82]">
                      {item.description}
                    </p>
                  </div>
                </li>
              )
            })}
          </ol>

          <p className="mt-8 rounded-lg bg-[#F0EFEA] p-3 text-[11px] leading-relaxed text-[#8C8A82]">
            Your progress is saved after each step. You can close this page and
            continue later.
          </p>
        </aside>

        <section className="rounded-2xl border border-[#E2E0D8] bg-white p-6 sm:p-8">
          <p className="text-[11px] font-semibold uppercase tracking-widest text-[#556B2F]">
            Step {step + 1} of {ONBOARDING_STEPS.length}
          </p>
          <h1 className="mt-2 font-display text-3xl font-semibold text-[#1C1C1C]">
            {currentStep.title}
          </h1>
          <p className="mt-1 text-sm text-[#8C8A82]">
            {currentStep.description}
          </p>

          <div className="mt-7 space-y-6">
            {step === 0 && (
              <>
                <Field
                  label="Display name"
                  hint="This is how your stylist will greet you."
                >
                  <TextInput
                    value={profileForm.display_name}
                    onChange={(event) =>
                      updateProfile("display_name", event.target.value)
                    }
                    placeholder="e.g. Sophia Laurent"
                    autoComplete="name"
                    disabled={saving}
                  />
                </Field>

                <div className="grid gap-5 sm:grid-cols-2">
                  <Field label="Preferred language">
                    <SelectInput
                      options={LANGUAGE_OPTIONS}
                      value={profileForm.preferred_language}
                      onChange={(event) =>
                        updateProfile("preferred_language", event.target.value)
                      }
                      disabled={saving}
                    />
                  </Field>
                  <Field label="Country">
                    <SelectInput
                      options={countryOptions}
                      value={profileForm.country}
                      onChange={(event) =>
                        updateProfile("country", event.target.value)
                      }
                      disabled={saving}
                    />
                  </Field>
                </div>

                <Field
                  label="City"
                  hint="Used for weather-aware recommendations."
                >
                  <TextInput
                    value={profileForm.city}
                    onChange={(event) =>
                      updateProfile("city", event.target.value)
                    }
                    placeholder="e.g. Tunis"
                    autoComplete="address-level2"
                    disabled={saving}
                  />
                </Field>
              </>
            )}

            {step === 1 && (
              <>
                <Field
                  label="Preferred fit"
                  hint="How you usually like clothes to sit."
                >
                  <SegmentedChoice
                    options={fitOptions}
                    value={preferencesForm.preferred_fit}
                    onChange={(value) =>
                      updatePreferences("preferred_fit", value)
                    }
                    disabled={saving}
                  />
                </Field>

                <Field label="Size system">
                  <div className="max-w-[220px]">
                    <SelectInput
                      options={SIZE_SYSTEM_OPTIONS}
                      value={profileForm.size_system}
                      onChange={(event) =>
                        updateProfile("size_system", event.target.value)
                      }
                      disabled={saving}
                    />
                  </div>
                </Field>

                <div>
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-[#8C8A82]">
                    Usual sizes
                  </p>
                  <div className="grid gap-4 sm:grid-cols-2">
                    {CLOTHING_SIZE_FIELDS.map((field) => (
                      <Field key={field.key} label={field.label}>
                        <TextInput
                          value={preferencesForm.clothing_sizes[field.key]}
                          onChange={(event) =>
                            updateSize(field.key, event.target.value)
                          }
                          placeholder={
                            field.key === "shoes" ? "e.g. EU 38" : "e.g. S"
                          }
                          disabled={saving}
                        />
                      </Field>
                    ))}
                  </div>
                  <p className="mt-2 text-xs text-[#8C8A82]">
                    Optional. Add only the sizes you want to use.
                  </p>
                </div>
              </>
            )}

            {step === 2 && (
              <>
                <Field label="Styles you love">
                  <MultiSelectChips
                    options={STYLE_OPTIONS}
                    value={preferencesForm.preferred_styles}
                    onChange={(value) =>
                      updatePreferences("preferred_styles", value)
                    }
                    disabled={saving}
                  />
                </Field>

                <Field label="Favourite colours">
                  <ColorMultiSelect
                    options={COLOR_OPTIONS}
                    value={preferencesForm.preferred_colors}
                    onChange={(value) =>
                      updatePreferences("preferred_colors", value)
                    }
                    disabled={saving}
                  />
                </Field>

                <Field label="Colours to avoid" hint="Optional.">
                  <ColorMultiSelect
                    options={COLOR_OPTIONS}
                    value={preferencesForm.avoided_colors}
                    onChange={(value) =>
                      updatePreferences("avoided_colors", value)
                    }
                    disabled={saving}
                  />
                </Field>

                <Field label="Occasions you dress for">
                  <MultiSelectChips
                    options={OCCASION_OPTIONS}
                    value={preferencesForm.preferred_occasions}
                    onChange={(value) =>
                      updatePreferences("preferred_occasions", value)
                    }
                    disabled={saving}
                  />
                </Field>

                <Field label="Favourite categories">
                  <MultiSelectChips
                    options={CATEGORY_OPTIONS}
                    value={preferencesForm.preferred_categories}
                    onChange={(value) =>
                      updatePreferences("preferred_categories", value)
                    }
                    disabled={saving}
                  />
                </Field>
              </>
            )}
          </div>

          {error && (
            <div className="mt-6">
              <Alert>{error}</Alert>
            </div>
          )}

          <div className="mt-8 flex flex-col-reverse gap-3 border-t border-[#E2E0D8] pt-6 sm:flex-row sm:items-center sm:justify-between">
            <button
              type="button"
              onClick={() =>
                step === 0
                  ? onSkip()
                  : setStep((current) => Math.max(0, current - 1))
              }
              disabled={saving}
              className="text-sm font-medium text-[#8C8A82] transition-colors hover:text-[#1C1C1C] disabled:opacity-50"
            >
              {step === 0 ? "Do this later" : "← Back"}
            </button>

            <button
              type="button"
              onClick={next}
              disabled={saving}
              className="flex items-center justify-center gap-2 rounded-lg bg-[#1C1C1C] px-6 py-3 text-sm font-semibold text-white transition-colors hover:bg-[#333] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {saving && <Spinner size={16} />}
              {saving
                ? "Saving…"
                : isLastStep
                  ? "Finish setup"
                  : "Save & continue"}
            </button>
          </div>
        </section>
      </main>
    </div>
  )
}
