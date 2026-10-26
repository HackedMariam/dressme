import { useEffect, useMemo, useState } from "react"
import { api } from "../../lib/api"
import { TAXONOMY, cap } from "../../lib/taxonomy"
import type { AccuracyRow } from "../../lib/types"
import { useUserData } from "../profile/UserDataProvider"
import { useWardrobe } from "../wardrobe/WardrobeProvider"

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

export default function DashboardPage() {
  const { items, health, loading, error } = useWardrobe()
  const { profile } = useUserData()
  const [accuracy, setAccuracy] = useState<AccuracyRow[]>([])

  useEffect(() => {
    let active = true
    api
      .accuracy()
      .then((rows) => {
        if (active) setAccuracy(rows)
      })
      .catch(() => {
        if (active) setAccuracy([])
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

    const avgConfidence = items.length
      ? items.reduce((sum, item) => sum + (item.confidence ?? 0), 0) / items.length
      : 0

    return {
      byGroup,
      colors,
      byOccasion,
      byStyle,
      avgConfidence,
      toReview: items.filter((item) => item.needs_review).length,
      confirmed: items.filter((item) => item.status === "confirmed").length,
    }
  }, [items])

  const displayName = profile?.display_name?.trim().split(/\s+/)[0] ?? ""
  const now = new Date()
  const dateLabel = now.toLocaleDateString("en", {
    weekday: "long",
    month: "long",
    day: "numeric",
  })

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">
          Good morning{displayName ? `, ${displayName}` : ""}.
        </h1>
        <p className="mt-1 text-sm text-[#8C8A82]">{dateLabel} - your wardrobe at a glance</p>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading && !items.length ? (
        <div className="flex min-h-[240px] items-center justify-center text-sm text-[#8C8A82]">
          Loading your wardrobe...
        </div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { label: "Total items", value: String(items.length), sub: "in your wardrobe" },
              { label: "To review", value: String(stats.toReview), sub: "need a quick check" },
              {
                label: "Avg. confidence",
                value: `${Math.round(stats.avgConfidence * 100)}%`,
                sub: "model detection",
              },
              {
                label: "AI classification",
                value: health?.llm ? "On" : "Off",
                sub: health?.llm ? health.llm_model ?? "LLM ready" : "rules only",
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
              {accuracy.length ? (
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
