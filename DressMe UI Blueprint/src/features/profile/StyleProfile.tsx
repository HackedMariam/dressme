import { useState, type ReactNode } from "react"
import { useAuth } from "../auth/AuthProvider"
import type { Page } from "../shell/navigation"
import ProfilePreferencesEditor from "./ProfilePreferencesEditor"
import { Alert, Spinner } from "./FormControls"
import { CLOTHING_SIZE_FIELDS, COLOR_OPTIONS } from "./options"
import { normalizeClothingSizes, parseLocation, userInitial } from "./types"
import UserAvatar, { useAvatarPhoto } from "./UserAvatar"
import { useUserData } from "./UserDataProvider"

function colorHex(name: string): string {
  return COLOR_OPTIONS.find((color) => color.value === name)?.hex ?? "#E2E0D8"
}

function Card({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-[#E2E0D8] bg-white p-6">
      <h3 className="font-display text-lg font-medium text-[#1C1C1C]">{title}</h3>
      {hint && <p className="mt-0.5 text-xs text-[#8C8A82]">{hint}</p>}
      <div className="mt-4">{children}</div>
    </section>
  )
}

function Empty({ text, onAdd }: { text: string; onAdd: () => void }) {
  return (
    <div className="rounded-lg border border-dashed border-[#E2E0D8] bg-[#FAF9F6] px-4 py-5 text-center">
      <p className="text-sm text-[#8C8A82]">{text}</p>
      <button type="button" onClick={onAdd} className="mt-1.5 text-xs font-semibold text-[#556B2F] hover:underline">
        Add now
      </button>
    </div>
  )
}

export default function StyleProfile({ onNavigate }: { onNavigate?: (page: Page) => void }) {
  const { profile, preferences, loading, error, refresh } = useUserData()
  const { user } = useAuth()
  const photo = useAvatarPhoto()
  const [editing, setEditing] = useState(false)
  const [saved, setSaved] = useState(false)

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-[#556B2F]">
          <Spinner size={26} />
          <p className="text-sm text-[#8C8A82]">Loading your style profile…</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="max-w-xl space-y-4">
        <Alert>{error}</Alert>
        <button
          type="button"
          onClick={() => void refresh()}
          className="rounded-lg bg-[#556B2F] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#6B8A3A]"
        >
          Try again
        </button>
      </div>
    )
  }

  const styles = preferences?.preferred_styles ?? []
  const colors = preferences?.preferred_colors ?? []
  const avoidedColors = preferences?.avoided_colors ?? []
  const occasions = preferences?.preferred_occasions ?? []
  const categories = preferences?.preferred_categories ?? []
  const sizes = normalizeClothingSizes(preferences?.clothing_sizes ?? null)
  const sizeEntries = CLOTHING_SIZE_FIELDS.filter((field) => sizes[field.key])
  const fit = preferences?.preferred_fit
  const displayName = profile?.display_name?.trim() || "Your profile"
  const place = parseLocation(profile?.location ?? null)
  const location = [place.city, place.country].filter(Boolean).join(", ")
  const archetype = styles[0]

  // How much of the profile is filled in: each missing part is named so the user knows what to add.
  const sections = [
    { label: "styles", done: styles.length > 0 },
    { label: "colours", done: colors.length > 0 },
    { label: "occasions", done: occasions.length > 0 },
    { label: "categories", done: categories.length > 0 },
    { label: "sizes", done: sizeEntries.length > 0 },
    { label: "fit", done: Boolean(fit) },
  ]
  const filled = sections.filter((section) => section.done).length
  const completeness = Math.round((filled / sections.length) * 100)
  const missing = sections.filter((section) => !section.done).map((section) => section.label)
  const startEditing = () => {
    setEditing(true)
    setSaved(false)
  }

  return (
    <div className="space-y-6">
      <section className="relative overflow-hidden rounded-3xl bg-[#1C1C1C] p-8 text-white">
        <div className="pointer-events-none absolute -right-20 -top-24 h-72 w-72 rounded-full bg-[#556B2F]/25 blur-3xl" />
        <div className="relative flex flex-wrap items-center gap-6">
          <UserAvatar
            initial={userInitial(profile?.display_name, user?.email)}
            photo={photo}
            size={112}
            className="ring-4 ring-[#556B2F]/60"
          />
          <div className="min-w-[220px] flex-1">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#8FAE5A]">Style profile</p>
            <h1 className="mt-1 font-display text-3xl font-semibold">{displayName}</h1>
            <p className="mt-1 text-sm text-white/55">
              {[user?.email, location].filter(Boolean).join(" · ")}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {archetype ? (
                <span className="rounded-full bg-[#556B2F] px-3 py-1 text-xs font-semibold capitalize">{archetype}</span>
              ) : (
                <span className="rounded-full border border-white/20 px-3 py-1 text-xs text-white/60">
                  No signature style yet
                </span>
              )}
              {styles.slice(1, 3).map((style) => (
                <span key={style} className="rounded-full border border-white/20 px-3 py-1 text-xs capitalize text-white/80">
                  {style}
                </span>
              ))}
            </div>
          </div>
          <div className="flex flex-col items-stretch gap-2">
            {!editing && (
              <button
                type="button"
                onClick={startEditing}
                className="rounded-lg bg-white px-5 py-2.5 text-sm font-semibold text-[#1C1C1C] transition-colors hover:bg-[#F0EFEA]"
              >
                Edit profile
              </button>
            )}
            {!photo && onNavigate && (
              <button
                type="button"
                onClick={() => onNavigate("avatar")}
                className="rounded-lg border border-white/25 px-5 py-2.5 text-xs font-semibold text-white/85 hover:bg-white/10"
              >
                Add your avatar
              </button>
            )}
          </div>
        </div>

        <div className="relative mt-7">
          <div className="flex items-center justify-between text-xs text-white/60">
            <span>Profile {completeness}% complete</span>
            {missing.length > 0 && <span>Still to add: {missing.join(", ")}</span>}
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/15">
            <div className="h-full rounded-full bg-[#8FAE5A] transition-all" style={{ width: `${completeness}%` }} />
          </div>
        </div>
      </section>

      {saved && <Alert tone="success">Your style preferences were saved.</Alert>}

      {editing && (
        <ProfilePreferencesEditor
          preferences={preferences}
          onCancel={() => setEditing(false)}
          onSaved={() => {
            setEditing(false)
            setSaved(true)
          }}
        />
      )}

      <div className="grid gap-5 lg:grid-cols-[1fr_300px]">
        <div className="space-y-5">
          <Card title="Style aesthetics" hint="The looks you are drawn to">
            {styles.length === 0 ? (
              <Empty text="No styles selected yet." onAdd={startEditing} />
            ) : (
              <div className="flex flex-wrap gap-2">
                {styles.map((style, index) => (
                  <span
                    key={style}
                    className={`rounded-full px-4 py-1.5 text-sm font-medium capitalize ${
                      index === 0 ? "bg-[#556B2F] text-white" : "bg-[#E8EDE0] text-[#556B2F]"
                    }`}
                  >
                    {style}
                  </span>
                ))}
              </div>
            )}
          </Card>

          <div className="grid gap-5 sm:grid-cols-2">
            <Card title="Favourite colours">
              {colors.length === 0 ? (
                <Empty text="No favourite colours saved." onAdd={startEditing} />
              ) : (
                <div className="flex flex-wrap gap-3">
                  {colors.map((color) => (
                    <div key={color} className="flex w-14 flex-col items-center gap-1">
                      <div
                        className="h-10 w-10 rounded-full border border-[#E2E0D8] shadow-sm"
                        style={{ backgroundColor: colorHex(color) }}
                      />
                      <span className="text-[10px] capitalize text-[#8C8A82]">{color}</span>
                    </div>
                  ))}
                </div>
              )}
              {avoidedColors.length > 0 && (
                <div className="mt-5 border-t border-[#E2E0D8] pt-4">
                  <p className="text-[10px] font-semibold uppercase tracking-widest text-[#8C8A82]">Avoiding</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {avoidedColors.map((color) => (
                      <span
                        key={color}
                        className="flex items-center gap-1.5 rounded-full border border-[#E2E0D8] bg-white px-2.5 py-1 text-[11px] capitalize text-[#8C8A82]"
                      >
                        <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: colorHex(color) }} />
                        {color}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </Card>

            <Card title="Preferred occasions">
              {occasions.length === 0 ? (
                <Empty text="No occasions saved." onAdd={startEditing} />
              ) : (
                <div className="flex flex-wrap gap-2">
                  {occasions.map((occasion) => (
                    <span key={occasion} className="rounded-full bg-[#F0EFEA] px-3 py-1.5 text-sm capitalize text-[#1C1C1C]">
                      {occasion}
                    </span>
                  ))}
                </div>
              )}
            </Card>
          </div>

          {categories.length > 0 && (
            <Card title="Preferred categories">
              <div className="flex flex-wrap gap-2">
                {categories.map((category) => (
                  <span key={category} className="rounded-full bg-[#E8EDE0] px-3 py-1 text-xs font-medium capitalize text-[#556B2F]">
                    {category}
                  </span>
                ))}
              </div>
            </Card>
          )}
        </div>

        <div className="space-y-5">
          <Card title="Size profile">
            {sizeEntries.length === 0 ? (
              <Empty text="No sizes saved yet." onAdd={startEditing} />
            ) : (
              <div className="grid grid-cols-2 gap-2">
                {sizeEntries.map((field) => (
                  <div key={field.key} className="rounded-lg bg-[#F0EFEA] px-3 py-2.5 text-center">
                    <p className="text-[10px] uppercase tracking-widest text-[#8C8A82]">{field.label}</p>
                    <p className="mt-0.5 font-display text-xl font-semibold text-[#1C1C1C]">{sizes[field.key]}</p>
                  </div>
                ))}
              </div>
            )}
            {fit && (
              <div className="mt-3 flex items-center justify-between rounded-lg border border-[#E2E0D8] px-3 py-2">
                <span className="text-xs text-[#8C8A82]">Preferred fit</span>
                <span className="text-xs font-semibold capitalize text-[#1C1C1C]">{fit}</span>
              </div>
            )}
          </Card>

          {onNavigate && (
            <div className="rounded-2xl border border-[#556B2F]/25 bg-[#E8EDE0] p-5">
              <p className="text-sm font-semibold text-[#1C1C1C]">Put it to use</p>
              <p className="mt-1 text-xs text-[#556B2F]">
                Your styles, colours and sizes shape every suggestion.
              </p>
              <div className="mt-3 flex flex-col gap-2">
                <button
                  type="button"
                  onClick={() => onNavigate("outfit-builder")}
                  className="rounded-lg bg-[#556B2F] px-3 py-2 text-xs font-semibold text-white hover:bg-[#6B8A3A]"
                >
                  Build an outfit
                </button>
                <button
                  type="button"
                  onClick={() => onNavigate("wardrobe-gaps")}
                  className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-[#1C1C1C] hover:bg-[#F0EFEA]"
                >
                  See what to buy
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
