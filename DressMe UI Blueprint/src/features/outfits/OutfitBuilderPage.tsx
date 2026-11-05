import { useEffect, useMemo, useState } from "react"
import { api, asset } from "../../lib/api"
import { tryOnGroup } from "../../lib/pieces"
import { TAXONOMY, cap } from "../../lib/taxonomy"
import type { AdviceSource, StylistWeather } from "../../lib/types"
import { parseLocation } from "../profile/types"
import { useUserData } from "../profile/UserDataProvider"
import type { Page } from "../shell/navigation"
import TryOnModal, { type OutfitTryOn } from "../shop/TryOnModal"
import { useWardrobe } from "../wardrobe/WardrobeProvider"
import { buildOutfits, currentSeason, type Outfit } from "./outfitBuilder"

const GROUP_ORDER = ["Outerwear", "Tops", "Dresses", "Bottoms", "Shoes"]

// Outfits composed from the user's own wardrobe by the outfit agent (real weather + wardrobe + fashion books).
// If the agent cannot answer, the local rule-based builder takes over so the page always shows something.
export default function OutfitBuilderPage({ onNavigate }: { onNavigate: (page: Page) => void }) {
  const { items, loading } = useWardrobe()
  const { profile } = useUserData()
  const place = parseLocation(profile?.location ?? null)
  const [occasion, setOccasion] = useState("everyday")
  const [season, setSeason] = useState(currentSeason)
  const [seed, setSeed] = useState(0)
  const [tryOn, setTryOn] = useState<OutfitTryOn | null>(null)

  const [agentOutfits, setAgentOutfits] = useState<Outfit[] | null>(null)
  const [agentMissing, setAgentMissing] = useState<string[]>([])
  const [weather, setWeather] = useState<StylistWeather | null>(null)
  const [sources, setSources] = useState<AdviceSource[]>([])
  const [thinking, setThinking] = useState(false)
  const [shown, setShown] = useState<string[][]>([])

  const local = useMemo(() => buildOutfits(items, { occasion, season }, 3, seed), [items, occasion, season, seed])

  const ready = items.length >= 3
  useEffect(() => {
    if (!ready) return
    let cancelled = false
    setThinking(true)
    api
      .outfitAgent({
        occasion,
        season,
        city: place.city || "Tunis",
        country: place.country || "Tunisia",
        unit: profile?.temperature_unit ?? "Celsius",
        avoid: seed ? shown.slice(-6) : [],
      })
      .then((reply) => {
        if (cancelled) return
        const byId = new Map(items.map((item) => [item.id, item]))
        const built: Outfit[] = reply.outfits
          .map((entry) => ({
            items: entry.items.map((id) => byId.get(id)).filter((item): item is NonNullable<typeof item> => Boolean(item)),
            score: 0,
            why: entry.why,
            title: entry.title,
            weatherNote: entry.weather_note,
          }))
          .filter((outfit) => outfit.items.length >= 2)
        setAgentOutfits(built.length ? built : null)
        setAgentMissing(reply.missing ?? [])
        setWeather(reply.weather ?? null)
        setSources(reply.sources ?? [])
        setShown((previous) => [...previous, ...built.map((outfit) => outfit.items.map((item) => item.id))])
      })
      .catch(() => {
        if (!cancelled) setAgentOutfits(null)
      })
      .finally(() => {
        if (!cancelled) setThinking(false)
      })
    return () => {
      cancelled = true
    }
    // The agent runs when the request changes (occasion, season, shuffle) or the wardrobe becomes usable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, occasion, season, seed])

  const usingAgent = agentOutfits !== null
  const outfits = usingAgent ? agentOutfits : local.outfits
  const missing = usingAgent ? agentMissing : local.missing

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Outfit Builder</h1>
          <p className="mt-1 text-sm text-[#8C8A82]">
            An AI agent builds ready-to-wear outfits from the clothes you own, the weather in your city and fashion books.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={occasion}
            onChange={(event) => {
              setOccasion(event.target.value)
              setShown([])
              setSeed(0)
            }}
            aria-label="Occasion"
            className="rounded-lg border border-[#E2E0D8] bg-white px-3 py-2 text-sm text-[#1C1C1C]"
          >
            {TAXONOMY.occasions.map((name) => (
              <option key={name} value={name}>
                {cap(name)}
              </option>
            ))}
          </select>
          <select
            value={season}
            onChange={(event) => {
              setSeason(event.target.value)
              setShown([])
              setSeed(0)
            }}
            aria-label="Season"
            className="rounded-lg border border-[#E2E0D8] bg-white px-3 py-2 text-sm text-[#1C1C1C]"
          >
            {TAXONOMY.seasons.map((name) => (
              <option key={name} value={name}>
                {cap(name)}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => setSeed((value) => value + 1)}
            disabled={thinking || !ready}
            className="rounded-lg bg-[#1C1C1C] px-4 py-2 text-sm font-semibold text-white hover:bg-[#333] disabled:opacity-40"
          >
            {thinking ? "Thinking..." : "Shuffle"}
          </button>
        </div>
      </div>

      {loading && !items.length && (
        <div className="flex min-h-[240px] items-center justify-center text-sm text-[#8C8A82]">
          Loading your wardrobe...
        </div>
      )}

      {ready && thinking && (
        <div className="flex items-center gap-3 rounded-xl border border-[#E2E0D8] bg-[#F0EFEA] px-5 py-4 text-sm text-[#1C1C1C]">
          <span className="h-2 w-2 animate-pulse rounded-full bg-[#556B2F]" />
          The agent is checking the weather, your wardrobe and the fashion books...
        </div>
      )}

      {usingAgent && weather && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-xl border border-[#E2E0D8] bg-white px-4 py-3 text-xs text-[#1C1C1C]">
          <span className="font-bold">Weather</span>
          <span className="font-semibold">
            {weather.city}, {weather.weekday}
          </span>
          <span>{cap(weather.condition)}</span>
          <span>
            {weather.temp_min}&deg; to {weather.temp_max}&deg;{weather.unit}
          </span>
          {weather.rain_chance_percent != null && <span>{weather.rain_chance_percent}% chance of rain</span>}
          {weather.wind_kmh != null && <span>Wind {weather.wind_kmh} km/h</span>}
        </div>
      )}

      {!loading && items.length < 3 && (
        <div className="rounded-xl border border-[#E2E0D8] bg-[#F0EFEA] px-6 py-10 text-center">
          <p className="font-medium text-[#1C1C1C]">Add a few more pieces first</p>
          <p className="mx-auto mt-1 max-w-sm text-sm text-[#8C8A82]">
            The builder needs at least a top, a bottom and shoes (or a dress) to compose an outfit.
          </p>
          <button
            type="button"
            onClick={() => onNavigate("wardrobe")}
            className="mt-4 rounded-lg bg-[#556B2F] px-4 py-2 text-xs font-semibold text-white hover:bg-[#6B8A3A]"
          >
            Add clothing
          </button>
        </div>
      )}

      {ready && !thinking && outfits.length === 0 && (
        <div className="rounded-xl border border-[#E2E0D8] bg-[#F0EFEA] px-6 py-10 text-center text-sm text-[#8C8A82]">
          Your wardrobe cannot make a complete outfit yet. Missing: {missing.join(", ")}.
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        {outfits.map((outfit, index) => (
          <article key={outfit.items.map((item) => item.id).join()} className="rounded-xl border border-[#E2E0D8] bg-white p-4">
            <p className="text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">Outfit {index + 1}</p>
            {outfit.title && <h2 className="mt-1 font-display text-lg font-semibold text-[#1C1C1C]">{outfit.title}</h2>}
            <div className="mt-3 grid grid-cols-2 gap-2">
              {[...outfit.items]
                .sort((a, b) => GROUP_ORDER.indexOf(a.category_group) - GROUP_ORDER.indexOf(b.category_group))
                .map((item) => (
                  <div key={item.id} className="rounded-lg bg-[#F0EFEA] p-2">
                    <div className="flex aspect-[4/5] items-center justify-center overflow-hidden">
                      {item.cutout_url ? (
                        <img
                          src={asset(item.cutout_url)}
                          alt={item.name}
                          loading="lazy"
                          className="h-full w-full object-contain"
                        />
                      ) : null}
                    </div>
                    <p className="mt-1.5 truncate text-[11px] font-semibold text-[#1C1C1C]">{item.name}</p>
                    <p className="truncate text-[10px] text-[#8C8A82]">{cap(item.color_name ?? item.category)}</p>
                  </div>
                ))}
            </div>
            <button
              type="button"
              disabled={!outfit.items.some((item) => tryOnGroup(item.category))}
              onClick={() => {
                const wearable = outfit.items.filter((item) => tryOnGroup(item.category) && item.cutout_url)
                setTryOn({
                  itemIds: wearable.map((item) => item.id),
                  previews: wearable.map((item) => asset(item.cutout_url)),
                })
              }}
              className="mt-3 w-full rounded-lg bg-[#1C1C1C] px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-black disabled:opacity-40"
            >
              Virtual try-on
            </button>
            {outfit.weatherNote && (
              <p className="mt-3 rounded-lg bg-[#F0EFEA] px-3 py-2 text-xs leading-relaxed text-[#1C1C1C]">
                <span className="font-bold">Weather: </span>
                {outfit.weatherNote}
              </p>
            )}
            {outfit.why.length > 0 && (
              <div className="mt-3">
                <p className="text-xs font-bold text-[#1C1C1C]">Why this outfit</p>
                <ul className="mt-1.5 space-y-1.5">
                  {outfit.why.map((reason) => (
                    <li key={reason} className="flex items-start gap-2 text-xs leading-relaxed text-[#1C1C1C]">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#556B2F]" />
                      <span>{reason}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </article>
        ))}
      </div>

      {usingAgent && sources.length > 0 && (
        <div className="rounded-xl border border-[#E2E0D8] bg-white px-4 py-3">
          <p className="text-xs font-bold text-[#1C1C1C]">From fashion books</p>
          <ul className="mt-1.5 space-y-1">
            {sources.map((source) => (
              <li key={source.marker} className="flex gap-2 text-[11px] text-[#1C1C1C]">
                <span className="shrink-0 font-semibold text-[#556B2F]">{source.marker.slice(1, -1)}</span>
                <span>
                  {source.title}
                  {source.page ? <span className="text-[#8C8A82]"> - p. {source.page}</span> : null}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {missing.length > 0 && outfits.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-900">
          <span>
            Better outfits are possible with {missing.join(" or ")}{usingAgent ? "" : " (your wardrobe has none for this occasion)"}.
          </span>
          <button
            type="button"
            onClick={() => onNavigate("wardrobe-gaps")}
            className="rounded-lg bg-[#1C1C1C] px-3 py-1.5 text-xs font-semibold text-white hover:bg-black"
          >
            See what to buy
          </button>
        </div>
      )}

      {tryOn && (
        <TryOnModal
          outfit={tryOn}
          label="Your outfit on your avatar"
          onClose={() => setTryOn(null)}
          onOpenAvatar={() => onNavigate("avatar")}
        />
      )}
    </div>
  )
}
