import { useMemo, useState, type ReactNode } from "react";
import { useAuth } from "../auth/AuthProvider";
import { Alert, SelectInput, Spinner, TextInput } from "../profile/FormControls";
import {
  COUNTRY_OPTIONS,
  CURRENCY_OPTIONS,
  LANGUAGE_OPTIONS,
  SIZE_SYSTEM_OPTIONS,
  TEMPERATURE_OPTIONS,
} from "../profile/options";
import { profileToInput, userInitial, type ProfileInput } from "../profile/types";
import { OwnAvatar } from "../profile/UserAvatar";
import { useUserData } from "../profile/UserDataProvider";
import { describeError, validateProfileInput } from "../profile/validation";
import type { Page } from "../shell/navigation";

function Toggle({ value, onChange, label }: { value: boolean; onChange: () => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={value}
      aria-label={label}
      onClick={onChange}
      className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${value ? "bg-[#556B2F]" : "bg-[#D5D2C8]"}`}
    >
      <span
        className={`absolute top-1 h-4 w-4 rounded-full bg-white shadow transition-all ${value ? "left-6" : "left-1"}`}
      />
    </button>
  );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-[#E2E0D8] bg-white">
      <div className="border-b border-[#EFEDE6] px-6 py-4">
        <h2 className="font-display text-lg font-medium text-[#1C1C1C]">{title}</h2>
        {hint && <p className="mt-0.5 text-xs text-[#8C8A82]">{hint}</p>}
      </div>
      <div className="divide-y divide-[#EFEDE6] px-6">{children}</div>
    </section>
  );
}

function Row({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 py-4">
      <div className="min-w-[200px] flex-1">
        <p className="text-sm font-medium text-[#1C1C1C]">{label}</p>
        {hint && <p className="mt-0.5 text-xs text-[#8C8A82]">{hint}</p>}
      </div>
      <div className="w-full sm:w-60">{children}</div>
    </div>
  );
}

export default function Settings({ onNavigate }: { onNavigate?: (page: Page) => void }) {
  const { user, signOut } = useAuth();
  const { profile, loading, error: loadError, saveProfile } = useUserData();
  const [form, setForm] = useState<ProfileInput>(() => profileToInput(profile));
  const [saving, setSaving] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [baseline, setBaseline] = useState(() => JSON.stringify(profileToInput(profile)));

  const dirty = useMemo(() => JSON.stringify(form) !== baseline, [form, baseline]);

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
      setBaseline(JSON.stringify(form));
      setSaved(true);
    } catch (saveError) {
      setError(describeError(saveError));
    } finally {
      setSaving(false);
    }
  };

  const discard = () => {
    setForm(JSON.parse(baseline) as ProfileInput);
    setError(null);
    setSaved(false);
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
  const name = form.display_name.trim() || "Your account";

  return (
    <div className="max-w-3xl space-y-6 pb-24">
      <div className="flex items-center gap-4">
        <OwnAvatar initial={userInitial(form.display_name, user?.email)} size={64} className="ring-2 ring-[#556B2F]/40" />
        <div>
          <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Settings</h1>
          <p className="mt-0.5 text-sm text-[#8C8A82]">
            {name}
            {user?.email ? ` · ${user.email}` : ""}
          </p>
        </div>
      </div>

      {saved && <Alert tone="success">Your settings were saved.</Alert>}
      {error && <Alert>{error}</Alert>}

      <Section title="Account" hint="How DressMe addresses you">
        <Row label="Full name">
          <TextInput
            value={form.display_name}
            onChange={(event) => update("display_name", event.target.value)}
            disabled={saving}
            autoComplete="name"
          />
        </Row>
        <Row label="Email" hint="Used to sign in. It cannot be changed here.">
          <TextInput value={user?.email ?? ""} readOnly className="bg-[#FAF9F6]" aria-label="Email address" />
        </Row>
        <Row label="Language">
          <SelectInput
            options={LANGUAGE_OPTIONS}
            value={form.preferred_language}
            onChange={(event) => update("preferred_language", event.target.value)}
            disabled={saving}
          />
        </Row>
      </Section>

      <Section title="Where you are" hint="Used for the local weather and for shops near you">
        <Row label="Country">
          <SelectInput
            options={countryOptions}
            value={form.country}
            onChange={(event) => update("country", event.target.value)}
            disabled={saving}
          />
        </Row>
        <Row label="City">
          <TextInput
            value={form.city}
            onChange={(event) => update("city", event.target.value)}
            placeholder="e.g. Tunis"
            disabled={saving}
            autoComplete="address-level2"
          />
        </Row>
      </Section>

      <Section title="Units" hint="How prices, temperatures and sizes are shown">
        <Row label="Currency">
          <SelectInput
            options={CURRENCY_OPTIONS}
            value={form.default_currency}
            onChange={(event) => update("default_currency", event.target.value)}
            disabled={saving}
          />
        </Row>
        <Row label="Temperature">
          <SelectInput
            options={TEMPERATURE_OPTIONS}
            value={form.temperature_unit}
            onChange={(event) => update("temperature_unit", event.target.value)}
            disabled={saving}
          />
        </Row>
        <Row label="Size system">
          <SelectInput
            options={SIZE_SYSTEM_OPTIONS}
            value={form.size_system}
            onChange={(event) => update("size_system", event.target.value)}
            disabled={saving}
          />
        </Row>
      </Section>

      <Section title="Notifications & AI" hint="What DressMe may do for you in the background">
        {[
          {
            label: "Daily outfit recommendations",
            sub: "Get your AI pick every morning",
            value: form.notifications_enabled,
            toggle: () => update("notifications_enabled", !form.notifications_enabled),
          },
          {
            label: "Weather sync",
            sub: "Adjust suggestions to the local forecast",
            value: form.weather_sync_enabled,
            toggle: () => update("weather_sync_enabled", !form.weather_sync_enabled),
          },
          {
            label: "AI style tips",
            sub: "Weekly wardrobe insights and gap analysis",
            value: form.ai_style_tips_enabled,
            toggle: () => update("ai_style_tips_enabled", !form.ai_style_tips_enabled),
          },
        ].map((setting) => (
          <div key={setting.label} className="flex items-center justify-between gap-4 py-4">
            <div>
              <p className="text-sm font-medium text-[#1C1C1C]">{setting.label}</p>
              <p className="mt-0.5 text-xs text-[#8C8A82]">{setting.sub}</p>
            </div>
            <Toggle value={setting.value} onChange={setting.toggle} label={setting.label} />
          </div>
        ))}
      </Section>

      <Section title="Privacy & session">
        <div className="flex flex-wrap items-center justify-between gap-3 py-4">
          <div className="min-w-[200px] flex-1">
            <p className="text-sm font-medium text-[#1C1C1C]">Your avatar photo</p>
            <p className="mt-0.5 text-xs text-[#8C8A82]">
              Stored privately for virtual try-ons. You can delete it at any time.
            </p>
          </div>
          {onNavigate && (
            <button
              type="button"
              onClick={() => onNavigate("avatar")}
              className="rounded-lg border border-[#E2E0D8] px-4 py-2 text-xs font-semibold text-[#1C1C1C] hover:bg-[#F0EFEA]"
            >
              Manage avatar
            </button>
          )}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 py-4">
          <div className="min-w-[200px] flex-1">
            <p className="text-sm font-medium text-[#1C1C1C]">Sign out</p>
            <p className="mt-0.5 text-xs text-[#8C8A82]">End your session on this device.</p>
          </div>
          <button
            type="button"
            onClick={logout}
            disabled={signingOut}
            className="rounded-lg border border-[#E2E0D8] px-4 py-2 text-xs font-semibold text-[#1C1C1C] hover:bg-[#F0EFEA] disabled:opacity-50"
          >
            {signingOut ? "Signing out..." : "Sign out"}
          </button>
        </div>
      </Section>

      {profile && !profile.onboarding_completed && (
        <Alert tone="info">
          Your profile setup is not finished yet. Use the "Complete profile setup" banner to continue where you
          left off.
        </Alert>
      )}

      <div className="sticky bottom-4 z-10 flex items-center justify-between gap-4 rounded-2xl border border-[#E2E0D8] bg-white/95 px-5 py-3 shadow-lg backdrop-blur">
        <p className="text-xs text-[#8C8A82]">{dirty ? "You have unsaved changes." : "All changes saved."}</p>
        <div className="flex items-center gap-2">
          {dirty && (
            <button
              type="button"
              onClick={discard}
              disabled={saving}
              className="rounded-lg px-4 py-2 text-sm font-semibold text-[#8C8A82] hover:text-[#1C1C1C] disabled:opacity-50"
            >
              Discard
            </button>
          )}
          <button
            type="button"
            onClick={save}
            disabled={saving || !dirty}
            className="flex items-center gap-2 rounded-lg bg-[#556B2F] px-6 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#6B8A3A] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving && <Spinner size={16} />}
            {saving ? "Saving..." : "Save changes"}
          </button>
        </div>
      </div>
    </div>
  );
}
