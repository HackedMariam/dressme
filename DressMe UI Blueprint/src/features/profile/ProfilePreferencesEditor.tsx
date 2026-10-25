import { useState } from "react"
import type { StyleProfileRow } from "../../lib/database.types"
import {
  Alert,
  ColorMultiSelect,
  Field,
  MultiSelectChips,
  SegmentedChoice,
  Spinner,
  TextInput,
} from "./FormControls"
import {
  CATEGORY_OPTIONS,
  CLOTHING_SIZE_FIELDS,
  COLOR_OPTIONS,
  FIT_OPTIONS,
  OCCASION_OPTIONS,
  STYLE_OPTIONS,
} from "./options"
import { preferencesToInput, type PreferencesInput } from "./types"
import { useUserData } from "./UserDataProvider"
import { describeError, validatePreferencesInput } from "./validation"

export default function ProfilePreferencesEditor({
  preferences,
  onSaved,
  onCancel,
}: {
  preferences: StyleProfileRow | null
  onSaved: () => void
  onCancel: () => void
}) {
  const { savePreferences } = useUserData()
  const [form, setForm] = useState<PreferencesInput>(() =>
    preferencesToInput(preferences),
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const update = <K extends keyof PreferencesInput,>(
    key: K,
    value: PreferencesInput[K],
  ) => {
    setForm((current) => ({ ...current, [key]: value }))
  }

  const updateSize = (
    key: keyof PreferencesInput["clothing_sizes"],
    value: string,
  ) => {
    setForm((current) => ({
      ...current,
      clothing_sizes: { ...current.clothing_sizes, [key]: value },
    }))
  }

  const save = async () => {
    if (saving) return
    setError(null)

    try {
      const patch = validatePreferencesInput(form)
      setSaving(true)
      await savePreferences(patch)
      onSaved()
    } catch (saveError) {
      setError(describeError(saveError))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="rounded-xl border border-[#E2E0D8] bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-lg font-medium text-[#1C1C1C]">
            Edit style profile
          </h3>
          <p className="mt-1 text-xs text-[#8C8A82]">
            Changes are saved to your DressMe account and used in
            recommendations.
          </p>
        </div>
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className="text-xs font-medium text-[#8C8A82] hover:text-[#1C1C1C] disabled:opacity-50"
        >
          Cancel
        </button>
      </div>

      <div className="mt-5 space-y-6">
        <Field label="Styles you love">
          <MultiSelectChips
            options={STYLE_OPTIONS}
            value={form.preferred_styles}
            onChange={(value) => update("preferred_styles", value)}
            disabled={saving}
          />
        </Field>

        <Field label="Favourite colours">
          <ColorMultiSelect
            options={COLOR_OPTIONS}
            value={form.preferred_colors}
            onChange={(value) => update("preferred_colors", value)}
            disabled={saving}
          />
        </Field>

        <Field label="Colours to avoid" hint="Optional.">
          <ColorMultiSelect
            options={COLOR_OPTIONS}
            value={form.avoided_colors}
            onChange={(value) => update("avoided_colors", value)}
            disabled={saving}
          />
        </Field>

        <Field label="Preferred occasions">
          <MultiSelectChips
            options={OCCASION_OPTIONS}
            value={form.preferred_occasions}
            onChange={(value) => update("preferred_occasions", value)}
            disabled={saving}
          />
        </Field>

        <Field label="Favourite categories">
          <MultiSelectChips
            options={CATEGORY_OPTIONS}
            value={form.preferred_categories}
            onChange={(value) => update("preferred_categories", value)}
            disabled={saving}
          />
        </Field>

        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Preferred fit">
            <SegmentedChoice
              options={[{ value: "", label: "No preference" }, ...FIT_OPTIONS]}
              value={form.preferred_fit}
              onChange={(value) => update("preferred_fit", value)}
              disabled={saving}
            />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            {CLOTHING_SIZE_FIELDS.map((field) => (
              <Field key={field.key} label={field.label}>
                <TextInput
                  value={form.clothing_sizes[field.key]}
                  onChange={(event) =>
                    updateSize(field.key, event.target.value)
                  }
                  placeholder={field.key === "shoes" ? "EU 38" : "S"}
                  disabled={saving}
                />
              </Field>
            ))}
          </div>
        </div>

        {error && <Alert>{error}</Alert>}

        <div className="flex justify-end gap-3 border-t border-[#E2E0D8] pt-4">
          <button
            type="button"
            onClick={onCancel}
            disabled={saving}
            className="rounded-lg border border-[#E2E0D8] px-5 py-2.5 text-sm font-semibold text-[#1C1C1C] transition-colors hover:bg-[#F0EFEA] disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="flex items-center gap-2 rounded-lg bg-[#556B2F] px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#6B8A3A] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {saving && <Spinner size={15} />}
            {saving ? "Saving…" : "Save preferences"}
          </button>
        </div>
      </div>
    </section>
  )
}
