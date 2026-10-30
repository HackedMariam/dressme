import { useEffect, useRef, useState } from "react"
import { api, asset } from "../../lib/api"
import type { AgentReply, WardrobeItem } from "../../lib/types"

export default function RecommendationCard({ items, onOpenWardrobe }: {
  items: WardrobeItem[]
  onOpenWardrobe: () => void
}) {
  const [recommendation, setRecommendation] = useState<AgentReply | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const requestId = useRef(0)

  useEffect(() => {
    setRecommendation(null)
    setError("")
    setBusy(false)
    return () => { requestId.current += 1 }
  }, [items])

  async function suggest() {
    const currentRequest = ++requestId.current
    setBusy(true)
    setError("")
    try {
      const result = await api.agentSearch("Suggest an everyday outfit using only items in my wardrobe. Explain your choices briefly.")
      if (currentRequest === requestId.current) setRecommendation(result)
    } catch (err) {
      if (currentRequest === requestId.current) setError(err instanceof Error ? err.message : "Could not reach the stylist. Please try again.")
    } finally {
      if (currentRequest === requestId.current) setBusy(false)
    }
  }

  const foundItems = (recommendation?.items ?? [])
    .map((found) => items.find((item) => item.id === found.id))
    .filter((item): item is WardrobeItem => Boolean(item))
    .slice(0, 3)
  const featured = foundItems.find((item) => item.cutout_url || item.image_url)

  return (
    <section className="flex min-h-[320px] flex-col overflow-hidden rounded-2xl bg-[#1C1C1C] sm:flex-row">
      <div className="flex flex-1 flex-col justify-between gap-6 p-8">
        <div>
          <span className="text-xs font-semibold uppercase tracking-widest text-[#8DAA5A]">AI Daily Recommendation</span>
          <h2 className="mt-3 font-display text-2xl font-medium leading-snug text-white">
            {recommendation ? "Your wardrobe, styled" : "An outfit from your wardrobe"}
          </h2>
          <p className="mt-3 max-w-lg whitespace-pre-line text-sm leading-relaxed text-white/60" aria-live="polite">
            {recommendation?.reply || (items.length
              ? "Let your stylist find pieces you already own for an everyday look."
              : "Add items to your wardrobe to get a personalised suggestion.")}
          </p>
          {error && <p role="alert" className="mt-3 text-sm text-red-300">{error}</p>}
        </div>
        <div className="space-y-4">
          {foundItems.length > 0 && <div>
            <p className="mb-2 text-[10px] uppercase tracking-wide text-white/40">Items found in your wardrobe</p>
            <div className="grid gap-2 sm:grid-cols-3">
              {foundItems.map((item) => <div key={item.id} className="rounded-lg bg-white/5 px-3 py-2 text-xs font-medium text-white/80">{item.name}</div>)}
            </div>
          </div>}
          {items.length ? <button type="button" onClick={() => void suggest()} disabled={busy} className="rounded-lg bg-[#556B2F] px-4 py-2.5 text-xs font-semibold text-white hover:bg-[#6B8A3A] disabled:opacity-50">
            {busy ? "Finding your look…" : recommendation ? "Suggest another look" : "Get a recommendation"}
          </button> : <button type="button" onClick={onOpenWardrobe} className="rounded-lg bg-[#556B2F] px-4 py-2.5 text-xs font-semibold text-white hover:bg-[#6B8A3A]">Open my wardrobe</button>}
        </div>
      </div>
      <div className="flex min-h-[180px] items-center justify-center bg-[#2A2A2A] p-5 sm:w-[280px]">
        {featured ? <img src={asset(featured.cutout_url || featured.image_url)} alt={featured.name} className="max-h-64 w-full object-contain" /> : <div className="text-center text-white/40"><span className="font-display text-6xl text-[#8DAA5A]">✦</span><p className="mt-3 text-xs">Made for your wardrobe</p></div>}
      </div>
    </section>
  )
}
