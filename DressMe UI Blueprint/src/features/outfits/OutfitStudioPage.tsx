import { useEffect, useMemo, useState } from "react"
import { api, asset } from "../../lib/api"
import { cap } from "../../lib/taxonomy"
import type { OutfitScore, WardrobeItem } from "../../lib/types"
import { useWardrobe } from "../wardrobe/WardrobeProvider"

const SCORED_CATEGORIES = new Set(["top", "sweater", "vest", "jacket", "pants", "shorts", "skirt", "dress"])
const FILTERS = ["All", "Tops", "Bottoms", "Dresses", "Outerwear", "Shoes", "Bags", "Accessories"]

function currentSeason() {
  const month = new Date().getMonth() + 1
  return month >= 3 && month <= 5 ? "spring" : month <= 8 && month >= 6 ? "summer" : month <= 11 && month >= 9 ? "autumn" : "winter"
}

function ItemImage({ item }: { item: WardrobeItem }) {
  const src = asset(item.cutout_url || item.image_url)
  const [failed, setFailed] = useState(false)
  useEffect(() => { setFailed(false) }, [src])
  if (!src || failed) return <div className="flex h-full items-center justify-center text-xs text-[#8C8A82]">No photo</div>
  return <img src={src} alt={item.name} onError={() => setFailed(true)} className="h-full w-full object-contain" />
}

function ScoreRing({ score }: { score: number }) {
  return <div className="relative flex h-20 w-20 shrink-0 items-center justify-center rounded-full" style={{ background: `conic-gradient(#8DAA5A ${Math.max(0, Math.min(score, 100))}%, #444 0)` }}>
    <div className="flex h-16 w-16 items-center justify-center rounded-full bg-[#1C1C1C] text-xl font-semibold text-white">{Math.round(score)}</div>
  </div>
}

export default function OutfitStudioPage({ onOpenWardrobe }: { onOpenWardrobe: () => void }) {
  const { items, loading, error, reload } = useWardrobe()
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [query, setQuery] = useState("")
  const [category, setCategory] = useState("All")
  const [occasion, setOccasion] = useState("casual")
  const [season, setSeason] = useState(currentSeason)
  const [score, setScore] = useState<OutfitScore | null>(null)
  const [scoring, setScoring] = useState(false)
  const [scoreError, setScoreError] = useState("")
  const [retry, setRetry] = useState(0)

  const selected = useMemo(() => selectedIds.flatMap((id) => {
    const item = items.find((entry) => entry.id === id)
    return item ? [item] : []
  }), [items, selectedIds])
  const scoredKey = selected.filter((item) => SCORED_CATEGORIES.has(item.category.toLowerCase())).map((item) => item.id).join(",")
  const excludedCount = selected.length - (scoredKey ? scoredKey.split(",").length : 0)
  const filtered = items.filter((item) => {
    const matchesCategory = category === "All" || item.category_group === category
    const text = [item.name, item.category, item.subcategory, item.color_name, item.style].filter(Boolean).join(" ").toLowerCase()
    return matchesCategory && text.includes(query.trim().toLowerCase())
  })

  useEffect(() => {
    let active = true
    setScore(null)
    setScoreError("")
    if (!scoredKey) { setScoring(false); return () => { active = false } }
    setScoring(true)
    const timer = window.setTimeout(() => {
      api.scoreOutfit(scoredKey.split(","), occasion, season)
        .then((result) => { if (active) setScore(result) })
        .catch((err) => { if (active) setScoreError(err instanceof Error ? err.message : "Unable to score this outfit.") })
        .finally(() => { if (active) setScoring(false) })
    }, 200)
    return () => { active = false; window.clearTimeout(timer) }
  }, [scoredKey, occasion, season, retry])

  function addItem(id: string) {
    setSelectedIds((previous) => previous.includes(id) || previous.length >= 10 ? previous : [...previous, id])
  }
  function removeItem(id: string) {
    setSelectedIds((previous) => previous.filter((entry) => entry !== id))
  }
  const suggestions = (score?.suggested_item_ids || []).flatMap((id) => {
    const item = items.find((entry) => entry.id === id)
    return item && !selectedIds.includes(id) ? [item] : []
  })

  return <div className="space-y-6">
    <header>
      <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Outfit Studio</h1>
      <p className="mt-1 text-sm text-[#8C8A82]">Build a look from your wardrobe and get feedback from the BO4 stylist.</p>
    </header>

    {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
      {error} <button type="button" onClick={() => void reload()} className="ml-2 underline">Retry wardrobe</button>
    </div>}
    {!loading && !error && !items.length && <div className="rounded-xl bg-[#F0EFEA] p-8 text-center">
      <p className="text-sm text-[#8C8A82]">Your wardrobe is empty. Add clothing to start building outfits.</p>
      <button type="button" onClick={onOpenWardrobe} className="mt-4 rounded-lg bg-[#556B2F] px-4 py-2 text-xs font-semibold text-white">Open My Wardrobe</button>
    </div>}

    {(loading || items.length > 0) && <div className="grid gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
      <section className="flex max-h-[720px] flex-col rounded-xl bg-[#F0EFEA] p-4" aria-label="Wardrobe items">
        <div className="flex items-center justify-between gap-2"><h2 className="text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">Your Wardrobe</h2><span className="text-xs text-[#8C8A82]">{items.length} {items.length === 1 ? "item" : "items"}</span></div>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search your wardrobe" aria-label="Search your wardrobe" className="mt-3 w-full rounded-lg border border-[#E2E0D8] bg-white px-3 py-2 text-sm outline-none focus:border-[#556B2F]" />
        <select value={category} onChange={(event) => setCategory(event.target.value)} aria-label="Filter by category" className="mt-2 w-full rounded-lg border border-[#E2E0D8] bg-white px-3 py-2 text-sm">
          {FILTERS.map((group) => <option key={group} value={group}>{group === "All" ? "All categories" : group}</option>)}
        </select>
        <div className="mt-3 min-h-[180px] space-y-1 overflow-y-auto">
          {loading ? <p className="p-3 text-sm text-[#8C8A82]">Loading your wardrobe…</p> : filtered.length === 0 ? <p className="p-3 text-sm text-[#8C8A82]">No items match these filters.</p> : filtered.map((item) => {
            const chosen = selectedIds.includes(item.id)
            return <button key={item.id} type="button" draggable={!chosen} onDragStart={(event) => event.dataTransfer.setData("text/plain", item.id)} onClick={() => addItem(item.id)} disabled={chosen || selectedIds.length >= 10}
              className="flex w-full items-center gap-3 rounded-lg p-2 text-left transition-colors hover:bg-[#E2E0D8] disabled:cursor-not-allowed disabled:opacity-40">
              <div className="h-12 w-10 shrink-0 overflow-hidden rounded bg-white"><ItemImage item={item} /></div>
              <div className="min-w-0 flex-1"><p className="truncate text-xs font-semibold text-[#1C1C1C]">{item.name}</p><p className="truncate text-[10px] text-[#8C8A82]">{item.category_group} · {item.color_name || "Color unknown"}</p></div>
              <span className="text-[#556B2F]">{chosen ? "✓" : "+"}</span>
            </button>
          })}
        </div>
      </section>

      <div className="space-y-4">
        <section className="min-h-[280px] rounded-xl bg-[#F0EFEA] p-6" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); const id = event.dataTransfer.getData("text/plain"); if (items.some((item) => item.id === id)) addItem(id) }}>
          <div className="flex items-center justify-between gap-3"><h2 className="text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">Outfit Canvas · {selected.length}/10</h2>
            <button type="button" onClick={() => setSelectedIds([])} disabled={!selected.length} className="text-xs text-[#8C8A82] hover:text-[#1C1C1C] disabled:opacity-40">Clear all</button></div>
          {!selected.length ? <div className="flex min-h-[200px] flex-col items-center justify-center text-center"><span className="text-3xl text-[#556B2F]">✦</span><p className="mt-3 text-sm text-[#8C8A82]">Select or drag items from your wardrobe</p></div> :
            <div className="mt-5 flex flex-wrap gap-4">{selected.map((item) => <div key={item.id} className="relative w-28">
              <div className="h-36 overflow-hidden rounded-xl bg-white"><ItemImage item={item} /></div>
              <button type="button" onClick={() => removeItem(item.id)} aria-label={`Remove ${item.name}`} className="absolute -right-2 -top-2 flex h-7 w-7 items-center justify-center rounded-full bg-[#1C1C1C] text-white">×</button>
              <p className="mt-2 truncate text-center text-xs font-medium text-[#1C1C1C]">{item.name}</p>
              {item.needs_review && <p className="text-center text-[10px] text-amber-700">Needs review</p>}
            </div>)}</div>}
        </section>

        <section className="rounded-xl bg-[#1C1C1C] p-5 text-white" aria-live="polite">
          <div className="flex flex-wrap items-end gap-3">
            <div className="mr-auto"><h2 className="text-xs font-semibold uppercase tracking-widest text-[#8DAA5A]">BO4 Style Compatibility</h2><p className="mt-1 text-xs text-white/50">A heuristic score, not a probability.</p></div>
            <label className="text-[10px] text-white/60">Occasion<select value={occasion} onChange={(event) => setOccasion(event.target.value)} className="mt-1 block rounded-lg border border-white/20 bg-[#2A2A2A] px-2 py-2 text-xs text-white">{["casual", "university", "work", "evening"].map((value) => <option key={value} value={value}>{cap(value)}</option>)}</select></label>
            <label className="text-[10px] text-white/60">Season<select value={season} onChange={(event) => setSeason(event.target.value)} className="mt-1 block rounded-lg border border-white/20 bg-[#2A2A2A] px-2 py-2 text-xs text-white">{["spring", "summer", "autumn", "winter"].map((value) => <option key={value} value={value}>{cap(value)}</option>)}</select></label>
          </div>
          <div className="mt-5">
            {scoring ? <p className="text-sm text-white/60">Scoring your outfit…</p> : scoreError ? <div role="alert" className="text-sm text-red-300">Could not score this outfit: {scoreError} <button type="button" onClick={() => setRetry((value) => value + 1)} className="underline">Retry</button><p className="mt-1 text-xs text-white/50">Make sure the updated BO4 stylist service is running.</p></div> : !scoredKey ? <p className="text-sm text-white/60">Add clothing to get feedback. BO4 scores tops, bottoms, dresses and outerwear.</p> : score && !score.complete ? <p className="text-sm text-white/70">{score.message}</p> : score?.score != null && <div className="flex flex-wrap items-center gap-5">
              <ScoreRing score={score.score} /><div className="flex-1"><p className="font-display text-xl">{score.score >= 85 ? "Strong combination" : score.score >= 65 ? "Good potential" : "Consider adjusting this look"}</p><p className="mt-1 text-xs text-white/50">Based on the selected clothing, occasion and season.</p>
                <div className="mt-3 flex flex-wrap gap-2">{[["Color", score.color_score], ["Style", score.style_score], ["Occasion", score.occasion_score], ["Season", score.season_score]].map(([label, value]) => <span key={label} className="rounded-lg bg-white/10 px-2 py-1 text-xs">{label}: {typeof value === "number" ? Math.round(value) : "—"}</span>)}</div>
              </div>
            </div>}
            {excludedCount > 0 && <p className="mt-4 text-xs text-white/50">Shoes and accessories are shown on your canvas but are not included in the BO4 score.</p>}
            {score?.explanations && score.explanations.length > 0 && <div className="mt-4 border-t border-white/10 pt-3"><p className="text-[10px] font-semibold uppercase tracking-widest text-white/40">Stylist reasoning · French</p><ul className="mt-2 space-y-1 text-xs text-white/70">{score.explanations.map((line, index) => <li key={`${line}-${index}`}>• {line}</li>)}</ul></div>}
            {suggestions.length > 0 && <div className="mt-4 border-t border-white/10 pt-3"><p className="text-[10px] font-semibold uppercase tracking-widest text-white/40">Complete your look with items you own</p><div className="mt-2 flex flex-wrap gap-2">{suggestions.map((item) => <button type="button" key={item.id} onClick={() => addItem(item.id)} disabled={selectedIds.length >= 10} className="rounded-lg bg-white/10 px-3 py-2 text-xs text-white/80 hover:bg-white/20 disabled:opacity-40">+ {item.name}</button>)}</div></div>}
          </div>
        </section>
      </div>
    </div>}
  </div>
}
