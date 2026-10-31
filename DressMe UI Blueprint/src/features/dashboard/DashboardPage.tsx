import { useEffect, useMemo, useState } from "react"
import { api } from "../../lib/api"
import { TAXONOMY, cap } from "../../lib/taxonomy"
import type { AccuracyRow } from "../../lib/types"
import { useUserData } from "../profile/UserDataProvider"
import { useWardrobe } from "../wardrobe/WardrobeProvider"
import { parseLocation } from "../profile/types"
import RecommendationCard from "./RecommendationCard"
import { wardrobeStats } from "./wardrobeStats"
import { fetchWeather, weatherIcon, weatherLabel, type WeatherResponse } from "../../api/weather"

function Bar({ label, value, total }: { label: string; value: number; total: number }) {
  const width = total ? Math.round((value / total) * 100) : 0
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-[#1C1C1C]">{label}</span>
        <span className="text-[#8C8A82]">{value}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-[#E2E0D8]">
        <div className="h-full rounded-full bg-[#556B2F]" style={{ width: `${width}%` }} />
      </div>
    </div>
  )
}

export default function DashboardPage({ onOpenGaps, onOpenWardrobe }: { onOpenGaps?: () => void; onOpenWardrobe: () => void }) {
  const { items, loading, error, reload } = useWardrobe()
  const { profile } = useUserData()
  const [accuracy, setAccuracy] = useState<AccuracyRow[] | null>(null)
  const [accuracyError, setAccuracyError] = useState(false)
  const [weather, setWeather] = useState<WeatherResponse | null>(null)
  const [weatherError, setWeatherError] = useState<string | null>(null)

  useEffect(() => {
    const location = parseLocation(profile?.location ?? null)
    const city = location.city.trim()
    if (!city) {
      setWeatherError("Add your city in Settings for live weather.")
      return
    }
    let active = true
    fetchWeather(city, location.country)
      .then((result) => active && setWeather(result))
      .catch((caught: Error) => active && setWeatherError(caught.message))
    return () => { active = false }
  }, [profile?.location])

  useEffect(() => {
    let active = true
    setAccuracy(null)
    setAccuracyError(false)
    api
      .accuracy()
      .then((rows) => {
        if (active) {
          setAccuracy(rows)
          setAccuracyError(false)
        }
      })
      .catch(() => {
        if (active) {
          setAccuracy([])
          setAccuracyError(true)
        }
      })
    return () => {
      active = false
    }
  }, [items])

  const stats = useMemo(() => {
    const byGroup = TAXONOMY.groups.map((group) => ({
      label: group,
      value: items.filter((item) => item.category_group === group).length,
    }))

    const colorMap = new Map<string, { count: number; hex: string }>()
    for (const item of items) {
      if (!item.color_name) continue
      const current = colorMap.get(item.color_name)
      colorMap.set(item.color_name, {
        count: (current?.count ?? 0) + 1,
        hex: item.color_hex ?? current?.hex ?? "#c8c8c8",
      })
    }
    const colors = [...colorMap.entries()].sort((a, b) => b[1].count - a[1].count)

    const byOccasion = TAXONOMY.occasions
      .map((occasion) => ({
        label: cap(occasion),
        value: items.filter((item) => (item.occasions ?? []).includes(occasion)).length,
      }))
      .filter((entry) => entry.value > 0)
      .sort((a, b) => b.value - a.value)

    const byStyle = TAXONOMY.styles
      .map((style) => ({
        label: cap(style),
        value: items.filter((item) => item.style === style).length,
      }))
      .filter((entry) => entry.value > 0)
      .sort((a, b) => b.value - a.value)

    return {
      ...wardrobeStats(items),
      byGroup,
      colors,
      byOccasion,
      byStyle,
    }
  }, [items])

  const displayName = profile?.display_name?.trim().split(/\s+/)[0] ?? ""
  const now = new Date()
  const dateLabel = now.toLocaleDateString("en", {
    weekday: "long",
    month: "long",
    day: "numeric",
  })
  const greeting = now.getHours() < 12 ? "Good morning" : now.getHours() < 18 ? "Good afternoon" : "Good evening"

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">
          {greeting}{displayName ? `, ${displayName}` : ""}.
        </h1>
        <p className="mt-1 text-sm text-[#8C8A82]">{dateLabel} - your wardrobe at a glance</p>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
          <button type="button" onClick={() => void reload()} className="ml-3 font-semibold underline">Try again</button>
        </div>
      )}

      <section className="rounded-2xl bg-[#1C1C1C] p-6 text-white">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-widest text-white/40">Live weather</p>
            <h2 className="mt-1 font-display text-xl font-medium">
              {weather ? `${weather.location.name}${weather.location.country ? `, ${weather.location.country}` : ""}` : "Your location"}
            </h2>
          </div>
          {weather && <span className="text-4xl">{weatherIcon(weather.current.weather_code)}</span>}
        </div>
        {weather ? (
          <div className="mt-4 flex items-end gap-4">
            <span className="font-display text-5xl font-light">{Math.round(weather.current.temperature_c ?? weather.days[0]?.temperature_max_c ?? 0)}°</span>
            <div className="pb-1 text-sm text-white/60">
              <p>{weatherLabel(weather.current.weather_code)}</p>
              <p>{Math.round(weather.days[0]?.temperature_min_c ?? 0)}° / {Math.round(weather.days[0]?.temperature_max_c ?? 0)}° today</p>
            </div>
          </div>
        ) : (
          <p className="mt-4 text-sm text-white/60">{weatherError ?? "Loading live forecast..."}</p>
        )}
        {weather?.warning && <p className="mt-3 text-xs text-amber-200">{weather.warning}</p>}
      </section>

      {loading && !items.length ? (
        <div className="flex min-h-[240px] items-center justify-center text-sm text-[#8C8A82]">
          Loading your wardrobe...
        </div>
      ) : error && !items.length ? null : (
        <>
          <RecommendationCard items={items} onOpenWardrobe={onOpenWardrobe} />

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { label: "Total items", value: String(items.length), sub: `across ${stats.categoryCount} ${stats.categoryCount === 1 ? "category" : "categories"}` },
              { label: "To review", value: String(stats.toReview), sub: "need a quick check" },
              { label: "Confirmed items", value: String(stats.confirmed), sub: "reviewed and confirmed" },
              {
                label: "Avg. confidence",
                value: stats.avgConfidence == null ? "—" : `${Math.round(stats.avgConfidence * 100)}%`,
                sub: stats.confidenceCount ? `detection · ${stats.confidenceCount} ${stats.confidenceCount === 1 ? "item" : "items"}` : "no detection data yet",
              },
            ].map((card) => (
              <div key={card.label} className="rounded-xl bg-[#F0EFEA] p-5">
                <p className="text-xs uppercase tracking-widest text-[#8C8A82]">{card.label}</p>
                <p className="mt-2 font-display text-3xl font-semibold text-[#1C1C1C]">
                  {card.value}
                </p>
                <p className="mt-1 text-xs text-[#8C8A82]">{card.sub}</p>
              </div>
            ))}
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <section className="rounded-xl bg-[#F0EFEA] p-6">
              <h2 className="font-display text-lg font-medium text-[#1C1C1C]">Potential overlaps</h2>
              <p className="mb-4 mt-1 text-xs text-[#8C8A82]">Items with the same category and colour; these are not necessarily duplicates.</p>
              {stats.overlaps.length ? stats.overlaps.slice(0, 4).map((group) => (
                <div key={JSON.stringify([group.category, group.color])} className="flex items-center justify-between gap-4 border-b border-[#E2E0D8] py-3 last:border-0">
                  <div>
                    <p className="text-xs font-medium text-[#1C1C1C]">{cap(group.color)} {group.category}</p>
                    <p className="mt-0.5 text-[10px] text-[#8C8A82]">{group.items.map((item) => item.name).join(", ")}</p>
                  </div>
                  <span className="shrink-0 rounded-full bg-[#E8EDE0] px-2 py-0.5 text-xs font-semibold text-[#556B2F]">{group.items.length} items</span>
                </div>
              )) : <p className="text-sm text-[#8C8A82]">No matching categories and colours found.</p>}
            </section>
            {onOpenGaps && <section className="rounded-xl bg-[#F0EFEA] p-6">
              <h2 className="font-display text-lg font-medium text-[#1C1C1C]">Wardrobe Gaps</h2>
              <p className="mt-1 text-xs text-[#8C8A82]">Explore the gap agent and its wardrobe analysis.</p>
              <button type="button" onClick={onOpenGaps} className="mt-4 text-xs font-semibold text-[#556B2F] hover:underline">Open agent →</button>
            </section>}

            <section className="rounded-xl bg-[#F0EFEA] p-6">
              <h2 className="font-display text-lg font-medium text-[#1C1C1C]">By category</h2>
              <p className="mb-4 mt-1 text-xs text-[#8C8A82]">How your wardrobe is distributed</p>
              <div className="space-y-3">
                {stats.byGroup.map((entry) => (
                  <Bar key={entry.label} label={entry.label} value={entry.value} total={items.length} />
                ))}
              </div>
            </section>

            <section className="rounded-xl bg-[#F0EFEA] p-6">
              <h2 className="font-display text-lg font-medium text-[#1C1C1C]">Colour palette</h2>
              <p className="mb-4 mt-1 text-xs text-[#8C8A82]">Your most common colours</p>
              {stats.colors.length ? (
                <div className="grid grid-cols-2 gap-2">
                  {stats.colors.slice(0, 10).map(([name, entry]) => (
                    <div
                      key={name}
                      className="flex items-center gap-2 rounded-lg bg-white px-3 py-2 text-xs text-[#1C1C1C]"
                    >
                      <span
                        className="h-4 w-4 rounded-full border border-[#E2E0D8]"
                        style={{ backgroundColor: entry.hex }}
                      />
                      <span className="flex-1 truncate">{cap(name)}</span>
                      <span className="font-semibold text-[#8C8A82]">{entry.count}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-[#8C8A82]">Add items to see your palette.</p>
              )}

              <h3 className="mb-3 mt-6 text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
                Season coverage
              </h3>
              <div className="space-y-3">
                {TAXONOMY.seasons.map((season) => {
                  const value = items.filter((item) => (item.seasons ?? []).includes(season)).length
                  return (
                    <Bar key={season} label={cap(season)} value={value} total={items.length} />
                  )
                })}
              </div>
            </section>

            <section className="rounded-xl bg-[#F0EFEA] p-6">
              <h2 className="font-display text-lg font-medium text-[#1C1C1C]">By occasion</h2>
              <p className="mb-4 mt-1 text-xs text-[#8C8A82]">What your wardrobe is ready for</p>
              {stats.byOccasion.length ? (
                <div className="space-y-3">
                  {stats.byOccasion.map((entry) => (
                    <Bar key={entry.label} label={entry.label} value={entry.value} total={items.length} />
                  ))}
                </div>
              ) : (
                <p className="text-sm text-[#8C8A82]">No occasion data yet.</p>
              )}

              <h3 className="mb-3 mt-6 text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
                By style
              </h3>
              {stats.byStyle.length ? (
                <div className="space-y-3">
                  {stats.byStyle.map((entry) => (
                    <Bar key={entry.label} label={entry.label} value={entry.value} total={items.length} />
                  ))}
                </div>
              ) : (
                <p className="text-sm text-[#8C8A82]">No style data yet.</p>
              )}
            </section>

            <section className="rounded-xl bg-[#F0EFEA] p-6">
              <h2 className="font-display text-lg font-medium text-[#1C1C1C]">
                Detection accuracy
              </h2>
              <p className="mb-4 mt-1 text-xs text-[#8C8A82]">
                Measured on items you reviewed. A field counts as wrong when you corrected it.
              </p>
              {accuracyError ? (
                <p className="text-sm text-[#8C8A82]">Detection accuracy is unavailable right now.</p>
              ) : accuracy === null ? (
                <p className="text-sm text-[#8C8A82]">Loading detection accuracy...</p>
              ) : accuracy.some((row) => row.reviewed > 0) ? (
                <div className="overflow-hidden rounded-lg border border-[#E2E0D8] bg-white">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-[#F0EFEA] text-[#8C8A82]">
                      <tr>
                        <th className="px-3 py-2 font-semibold">Field</th>
                        <th className="px-3 py-2 font-semibold">Reviewed</th>
                        <th className="px-3 py-2 font-semibold">Corrected</th>
                        <th className="px-3 py-2 font-semibold">Accuracy</th>
                      </tr>
                    </thead>
                    <tbody>
                      {accuracy.map((row) => (
                        <tr key={row.field} className="border-t border-[#E2E0D8]">
                          <td className="px-3 py-2 text-[#1C1C1C]">
                            {cap(row.field.replace(/_/g, " "))}
                          </td>
                          <td className="px-3 py-2 text-[#8C8A82]">{row.reviewed}</td>
                          <td className="px-3 py-2 text-[#8C8A82]">{row.corrected}</td>
                          <td className="px-3 py-2 font-semibold text-[#1C1C1C]">
                            {row.accuracy == null ? "-" : `${Math.round(row.accuracy * 100)}%`}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-sm text-[#8C8A82]">
                  Review and confirm a few items to see real accuracy numbers.
                </p>
              )}
              <p className="mt-3 text-xs text-[#8C8A82]">
                {stats.confirmed} item{stats.confirmed === 1 ? "" : "s"} confirmed so far.
              </p>
            </section>
          </div>
        </>
      )}
    </div>
  )
}
