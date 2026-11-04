import { useMemo, type ReactNode } from "react"
import { COLORS, TAXONOMY, cap } from "../../lib/taxonomy"
import { useWardrobe } from "../wardrobe/WardrobeProvider"

function Panel({ title, hint, children }: { title: string; hint: string; children: ReactNode }) {
  return (
    <div>
      <h3 className="font-display text-base font-medium text-[#1C1C1C]">{title}</h3>
      <p className="mb-4 mt-0.5 text-xs text-[#8C8A82]">{hint}</p>
      {children}
    </div>
  )
}

function Chip({ label, count }: { label: string; count: number }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-[#F0EFEA] px-3 py-1 text-xs text-[#1C1C1C]">
      {label}
      <span className="font-semibold text-[#556B2F]">{count}</span>
    </span>
  )
}

// The wardrobe at a glance: what is owned, in which colours, and what it is ready for.
export default function WardrobeInsights() {
  const { items } = useWardrobe()

  const data = useMemo(() => {
    const count = (predicate: (item: (typeof items)[number]) => boolean) => items.filter(predicate).length
    const groups = TAXONOMY.groups.map((group) => ({ label: group, value: count((item) => item.category_group === group) }))

    const palette = new Map<string, { count: number; hex: string }>()
    for (const item of items) {
      if (!item.color_name) continue
      const current = palette.get(item.color_name)
      palette.set(item.color_name, {
        count: (current?.count ?? 0) + 1,
        hex: COLORS[item.color_name] ?? item.color_hex ?? current?.hex ?? "#c8c8c8",
      })
    }
    const colors = [...palette.entries()].sort((a, b) => b[1].count - a[1].count)

    const ranked = (names: readonly string[], key: (item: (typeof items)[number], name: string) => boolean) =>
      names
        .map((name) => ({ label: cap(name), value: count((item) => key(item, name)) }))
        .filter((entry) => entry.value > 0)
        .sort((a, b) => b.value - a.value)

    return {
      groups,
      colors,
      seasons: TAXONOMY.seasons.map((season) => ({
        label: cap(season),
        value: count((item) => (item.seasons ?? []).includes(season)),
      })),
      occasions: ranked(TAXONOMY.occasions, (item, name) => (item.occasions ?? []).includes(name)),
      styles: ranked(TAXONOMY.styles, (item, name) => item.style === name),
    }
  }, [items])

  if (!items.length) return null
  const top = Math.max(1, ...data.groups.map((entry) => entry.value))
  const paletteTotal = data.colors.reduce((sum, [, entry]) => sum + entry.count, 0)

  return (
    <section className="rounded-2xl border border-[#E2E0D8] bg-white p-6">
      <h2 className="font-display text-lg font-medium text-[#1C1C1C]">Your wardrobe at a glance</h2>
      <div className="mt-5 grid gap-8 lg:grid-cols-3">
        <Panel title="What you own" hint="By type of clothing">
          <div className="space-y-2.5">
            {data.groups.map((entry) => (
              <div key={entry.label} className="flex items-center gap-3 text-xs">
                <span className="w-20 shrink-0 text-[#1C1C1C]">{entry.label}</span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-[#F0EFEA]">
                  <div
                    className={`h-full rounded-full ${entry.value ? "bg-[#556B2F]" : ""}`}
                    style={{ width: `${(entry.value / top) * 100}%` }}
                  />
                </div>
                <span className="w-6 text-right font-semibold text-[#8C8A82]">{entry.value}</span>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Colour palette" hint="Your most worn shades">
          {data.colors.length ? (
            <>
              <div className="flex h-9 overflow-hidden rounded-lg border border-[#E2E0D8]">
                {data.colors.slice(0, 12).map(([name, entry]) => (
                  <div
                    key={name}
                    title={`${cap(name)}: ${entry.count}`}
                    style={{ backgroundColor: entry.hex, width: `${(entry.count / paletteTotal) * 100}%` }}
                  />
                ))}
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {data.colors.slice(0, 8).map(([name, entry]) => (
                  <span key={name} className="inline-flex items-center gap-1.5 rounded-full bg-[#F0EFEA] px-2.5 py-1 text-xs text-[#1C1C1C]">
                    <span className="h-2.5 w-2.5 rounded-full border border-black/10" style={{ backgroundColor: entry.hex }} />
                    {cap(name)}
                  </span>
                ))}
              </div>
            </>
          ) : (
            <p className="text-sm text-[#8C8A82]">Add clothes to see your palette.</p>
          )}
        </Panel>

        <Panel title="Ready for" hint="Seasons, occasions and styles">
          <div className="grid grid-cols-4 gap-2">
            {data.seasons.map((season) => (
              <div key={season.label} className="rounded-lg bg-[#F0EFEA] px-2 py-2 text-center">
                <p className="font-display text-lg font-semibold text-[#1C1C1C]">{season.value}</p>
                <p className="text-[10px] text-[#8C8A82]">{season.label}</p>
              </div>
            ))}
          </div>
          {data.occasions.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-1.5">
              {data.occasions.slice(0, 6).map((entry) => (
                <Chip key={entry.label} label={entry.label} count={entry.value} />
              ))}
            </div>
          )}
          {data.styles.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {data.styles.slice(0, 4).map((entry) => (
                <Chip key={entry.label} label={entry.label} count={entry.value} />
              ))}
            </div>
          )}
        </Panel>
      </div>
    </section>
  )
}
