import { useState } from "react";
import { useAuth } from "../auth/AuthProvider";
import { Alert, SelectInput, Spinner, TextInput } from "../profile/FormControls";
import {
  COUNTRY_OPTIONS,
  CURRENCY_OPTIONS,
  LANGUAGE_OPTIONS,
  SIZE_SYSTEM_OPTIONS,
  TEMPERATURE_OPTIONS,
} from "../profile/options";
import { profileToInput, type ProfileInput } from "../profile/types";
import { useUserData } from "../profile/UserDataProvider";
import { describeError, validateProfileInput } from "../profile/validation";

function Toggle({ value, onChange }: { value: boolean; onChange: () => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={value}
      onClick={onChange}
      className={`relative h-6 w-10 rounded-full transition-colors ${value ? "bg-[#556B2F]" : "bg-[#E2E0D8]"}`}
    >
      <span
        className={`absolute top-1 h-4 w-4 rounded-full bg-white shadow transition-transform ${value ? "left-5" : "left-1"}`}
      />
    </button>
  );
}

export default function Settings() {
  const { user, signOut } = useAuth();
  const { profile, loading, error: loadError, saveProfile } = useUserData();
  const [form, setForm] = useState<ProfileInput>(() => profileToInput(profile));
  const [saving, setSaving] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-[#556B2F]">
          <Spinner size={26} />
          <p className="text-sm text-[#8C8A82]">Loading your settings...</p>
        </div>
      </div>
    );
  }

  if (loadError) {
    return <Alert>{loadError}</Alert>;
  }

  const update = <K extends keyof ProfileInput>(key: K, value: ProfileInput[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
    setSaved(false);
  };

  const save = async () => {
    if (saving) return;
    setError(null);
    setSaved(false);

    try {
      const patch = validateProfileInput(form);
      setSaving(true);
      await saveProfile(patch);
      setSaved(true);
    } catch (saveError) {
      setError(describeError(saveError));
    } finally {
      setSaving(false);
    }
  };

  const logout = async () => {
    if (signingOut) return;
    setError(null);
    try {
      setSigningOut(true);
      await signOut();
    } catch (signOutError) {
      setError(describeError(signOutError));
      setSigningOut(false);
    }
  };

  const countryOptions = [{ value: "", label: "Select a country" }, ...COUNTRY_OPTIONS];

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Settings</h1>
        <p className="mt-1 text-sm text-[#8C8A82]">Manage your account and preferences</p>
      </div>

      {saved && <Alert tone="success">Your settings were saved.</Alert>}
      {error && <Alert>{error}</Alert>}

      <div className="space-y-4 rounded-xl bg-[#F0EFEA] p-6">
        <h3 className="font-display text-lg font-medium text-[#1C1C1C]">Account</h3>

        <div className="flex items-center justify-between gap-4">
          <label className="text-sm font-medium text-[#1C1C1C]">Full Name</label>
          <TextInput
            value={form.display_name}
            onChange={(event) => update("display_name", event.target.value)}
            className="w-56"
            disabled={saving}
            autoComplete="name"
          />
        </div>

        <div className="flex items-center justify-between gap-4">
          <label className="text-sm font-medium text-[#1C1C1C]">Email</label>
          <TextInput
            value={user?.email ?? ""}
            readOnly
            className="w-56 bg-[#FAF9F6]"
            aria-label="Email address"
          />
        </div>

        <div className="flex items-center justify-between gap-4">
          <label className="text-sm font-medium text-[#1C1C1C]">Preferred Language</label>
          <div className="w-56">
            <SelectInput
              options={LANGUAGE_OPTIONS}
              value={form.preferred_language}
              onChange={(event) => update("preferred_language", event.target.value)}
              disabled={saving}
            />
          </div>
        </div>

        <div className="flex items-center justify-between gap-4">
          <label className="text-sm font-medium text-[#1C1C1C]">Country</label>
          <div className="w-56">
            <SelectInput
              options={countryOptions}
              value={form.country}
              onChange={(event) => update("country", event.target.value)}
              disabled={saving}
            />
          </div>
        </div>

        <div className="flex items-center justify-between gap-4">
          <label className="text-sm font-medium text-[#1C1C1C]">City</label>
          <TextInput
            value={form.city}
            onChange={(event) => update("city", event.target.value)}
            className="w-56"
            placeholder="e.g. Tunis"
            disabled={saving}
            autoComplete="address-level2"
          />
        </div>

        <div className="border-t border-[#E2E0D8] pt-4">
          <button
            type="button"
            onClick={logout}
            disabled={signingOut}
            className="text-sm font-semibold text-[#8C8A82] transition-colors hover:text-[#1C1C1C] disabled:opacity-50"
          >
            {signingOut ? "Signing out..." : "Sign out"}
          </button>
        </div>
      </div>

      <div className="space-y-4 rounded-xl bg-[#F0EFEA] p-6">
        <h3 className="font-display text-lg font-medium text-[#1C1C1C]">Preferences</h3>

        <div className="flex items-center justify-between gap-4">
          <label className="text-sm font-medium text-[#1C1C1C]">Default Currency</label>
          <div className="w-56">
            <SelectInput
              options={CURRENCY_OPTIONS}
              value={form.default_currency}
              onChange={(event) => update("default_currency", event.target.value)}
              disabled={saving}
            />
          </div>
        </div>

        <div className="flex items-center justify-between gap-4">
          <label className="text-sm font-medium text-[#1C1C1C]">Temperature Unit</label>
          <div className="w-56">
            <SelectInput
              options={TEMPERATURE_OPTIONS}
              value={form.temperature_unit}
              onChange={(event) => update("temperature_unit", event.target.value)}
              disabled={saving}
            />
          </div>
        </div>

        <div className="flex items-center justify-between gap-4">
          <label className="text-sm font-medium text-[#1C1C1C]">Size System</label>
          <div className="w-56">
            <SelectInput
              options={SIZE_SYSTEM_OPTIONS}
              value={form.size_system}
              onChange={(event) => update("size_system", event.target.value)}
              disabled={saving}
            />
          </div>
        </div>
      </div>

      <div className="space-y-4 rounded-xl bg-[#F0EFEA] p-6">
        <h3 className="font-display text-lg font-medium text-[#1C1C1C]">Notifications & AI</h3>

        {[
          {
            label: "Daily Outfit Recommendations",
            sub: "Get your AI pick every morning",
            value: form.notifications_enabled,
            toggle: () => update("notifications_enabled", !form.notifications_enabled),
          },
          {
            label: "Weather Sync",
            sub: "Auto-adjust suggestions for local forecast",
            value: form.weather_sync_enabled,
            toggle: () => update("weather_sync_enabled", !form.weather_sync_enabled),
          },
          {
            label: "AI Style Tips",
            sub: "Weekly wardrobe insights and gap analysis",
            value: form.ai_style_tips_enabled,
            toggle: () => update("ai_style_tips_enabled", !form.ai_style_tips_enabled),
          },
        ].map((setting) => (
          <div key={setting.label} className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-[#1C1C1C]">{setting.label}</p>
              <p className="text-xs text-[#8C8A82]">{setting.sub}</p>
            </div>
            <Toggle value={setting.value} onChange={setting.toggle} />
          </div>
        ))}
      </div>

      {profile && !profile.onboarding_completed && (
        <Alert tone="info">
          Your profile setup is not finished yet. Use the "Complete profile setup" banner to
          continue where you left off.
        </Alert>
      )}

      <button
        type="button"
        onClick={save}
        disabled={saving}
        className="flex items-center gap-2 rounded-lg bg-[#556B2F] px-8 py-3 text-sm font-semibold text-white transition-colors hover:bg-[#6B8A3A] disabled:cursor-not-allowed disabled:opacity-60"
      >
        {saving && <Spinner size={16} />}
        {saving ? "Saving..." : "Save Changes"}
      </button>
    </div>
  );
}
