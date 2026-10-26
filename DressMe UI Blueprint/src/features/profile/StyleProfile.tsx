import { useState } from "react"
import ProfilePreferencesEditor from "./ProfilePreferencesEditor"
import { Alert, Spinner } from "./FormControls"
import { CLOTHING_SIZE_FIELDS, COLOR_OPTIONS } from "./options"
import { normalizeClothingSizes } from "./types"
import { useUserData } from "./UserDataProvider"

const EDITORIAL_IMG =
  "https://images.unsplash.com/photo-1683392969197-17547ac3e06e?w=600&h=800&fit=crop&auto=format"

function colorHex(name: string): string {
  return COLOR_OPTIONS.find((color) => color.value === name)?.hex ?? "#E2E0D8"
}

export default function StyleProfile() {
  const { profile, preferences, loading, error, refresh } = useUserData()
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
  const displayName = profile?.display_name?.trim()
  const archetype = styles[0] ?? "Build your signature"
  const fit = preferences?.preferred_fit

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">
            Style Profile
          </h1>
          <p className="mt-1 text-sm text-[#8C8A82]">
            Your taste, preferences, and aesthetic fingerprint
          </p>
        </div>
        {!editing && (
          <button
            type="button"
            onClick={() => {
              setEditing(true)
              setSaved(false)
            }}
            className="rounded-lg border border-[#E2E0D8] bg-white px-5 py-2.5 text-sm font-semibold text-[#1C1C1C] transition-colors hover:border-[#556B2F]"
          >
            Edit style profile
          </button>
        )}
      </div>

      {saved && (
        <Alert tone="success">Your style preferences were saved.</Alert>
      )}

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

      <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
        <div className="space-y-5">
          <div className="rounded-xl bg-[#F0EFEA] p-6">
            <h3 className="font-display text-lg font-medium text-[#1C1C1C]">
              Style Aesthetics
            </h3>
            <p className="mt-1 text-xs text-[#8C8A82]">
              Selected in your DressMe profile
            </p>

            {styles.length === 0 ? (
              <div className="mt-5 rounded-lg border border-dashed border-[#E2E0D8] bg-white/60 px-4 py-6 text-center">
                <p className="text-sm text-[#8C8A82]">
                  No styles selected yet.
                </p>
                <button
                  type="button"
                  onClick={() => setEditing(true)}
                  className="mt-2 text-xs font-semibold text-[#556B2F] hover:underline"
                >
                  Add your styles →
                </button>
              </div>
            ) : (
              <div className="mt-5 space-y-3">
                {styles.map((style) => (
                  <div key={style}>
                    <div className="mb-1.5 flex items-center justify-between text-sm">
                      <span className="font-medium text-[#1C1C1C]">
                        {style}
                      </span>
                      <span className="text-xs font-semibold text-[#556B2F]">
                        Selected
                      </span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-[#E2E0D8]">
                      <div className="h-full w-full rounded-full bg-[#556B2F]" />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            <div className="rounded-xl bg-[#F0EFEA] p-6">
              <h3 className="font-display text-lg font-medium text-[#1C1C1C]">
                Favourite Colors
              </h3>
              {colors.length === 0 ? (
                <p className="mt-4 text-sm text-[#8C8A82]">
                  No favourite colours saved.
                </p>
              ) : (
                <div className="mt-4 flex flex-wrap gap-3">
                  {colors.map((color) => (
                    <div
                      key={color}
                      className="flex flex-col items-center gap-1"
                    >
                      <div
                        className="h-8 w-8 rounded-full border border-[#E2E0D8]"
                        style={{ backgroundColor: colorHex(color) }}
                      />
                      <span className="text-[9px] text-[#8C8A82]">{color}</span>
                    </div>
                  ))}
                </div>
              )}

              {avoidedColors.length > 0 && (
                <div className="mt-5 border-t border-[#E2E0D8] pt-4">
                  <p className="text-[10px] font-semibold uppercase tracking-widest text-[#8C8A82]">
                    Avoiding
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {avoidedColors.map((color) => (
                      <span
                        key={color}
                        className="rounded-full border border-[#E2E0D8] bg-white px-2 py-0.5 text-[10px] text-[#8C8A82]"
                      >
                        {color}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="rounded-xl bg-[#F0EFEA] p-6">
              <h3 className="font-display text-lg font-medium text-[#1C1C1C]">
                Preferred Occasions
              </h3>
              {occasions.length === 0 ? (
                <p className="mt-4 text-sm text-[#8C8A82]">
                  No occasions saved.
                </p>
              ) : (
                <div className="mt-3">
                  {occasions.map((occasion) => (
                    <div
                      key={occasion}
                      className="flex items-center gap-2 py-1.5"
                    >
                      <div className="h-1.5 w-1.5 rounded-full bg-[#556B2F]" />
                      <span className="text-sm text-[#1C1C1C]">{occasion}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {categories.length > 0 && (
            <div className="rounded-xl bg-[#F0EFEA] p-6">
              <h3 className="font-display text-lg font-medium text-[#1C1C1C]">
                Preferred Categories
              </h3>
              <div className="mt-3 flex flex-wrap gap-2">
                {categories.map((category) => (
                  <span
                    key={category}
                    className="rounded-full bg-[#E8EDE0] px-3 py-1 text-xs font-medium text-[#556B2F]"
                  >
                    {category}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="space-y-4">
          <div className="relative h-52 overflow-hidden rounded-2xl bg-[#1C1C1C]">
            <img
              src={EDITORIAL_IMG}
              alt="Style profile editorial"
              className="h-full w-full object-cover opacity-70"
            />
            <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent p-5">
              <p className="text-xs text-white/60">
                {displayName
                  ? `${displayName}'s Style Archetype`
                  : "Your Style Archetype"}
              </p>
              <p className="font-display text-xl font-medium text-white">
                {archetype}
              </p>
            </div>
          </div>

          <div className="rounded-xl bg-[#F0EFEA] p-5">
            <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
              Size Profile
            </p>
            {sizeEntries.length === 0 ? (
              <p className="text-sm text-[#8C8A82]">No sizes saved yet.</p>
            ) : (
              sizeEntries.map((field) => (
                <div
                  key={field.key}
                  className="flex justify-between border-b border-[#E2E0D8] py-2 last:border-0"
                >
                  <span className="text-xs text-[#8C8A82]">{field.label}</span>
                  <span className="text-xs font-semibold text-[#1C1C1C]">
                    {sizes[field.key]}
                  </span>
                </div>
              ))
            )}
            {fit && (
              <div className="mt-2 flex justify-between border-t border-[#E2E0D8] pt-3">
                <span className="text-xs text-[#8C8A82]">Preferred fit</span>
                <span className="text-xs font-semibold capitalize text-[#1C1C1C]">
                  {fit}
                </span>
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={() => {
              setEditing(true)
              setSaved(false)
            }}
            className="w-full rounded-lg bg-[#556B2F] py-3 text-sm font-semibold text-white transition-colors hover:bg-[#6B8A3A]"
          >
            Edit Profile
          </button>
        </div>
      </div>
    </div>
  )
}
