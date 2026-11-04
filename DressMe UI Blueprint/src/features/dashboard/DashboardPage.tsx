import { useEffect, useMemo, useState } from "react"
import { api } from "../../lib/api"
import { TAXONOMY, cap } from "../../lib/taxonomy"
import type { AccuracyRow } from "../../lib/types"
import { userInitial } from "../profile/types"
import { OwnAvatar } from "../profile/UserAvatar"
import { useUserData } from "../profile/UserDataProvider"
import { useWardrobe } from "../wardrobe/WardrobeProvider"
import { useAuth } from "../auth/AuthProvider"
import type { Page } from "../shell/navigation"
import OutfitsToBuy from "../shop/OutfitsToBuy"
import GapsCard from "../wardrobegaps/GapsCard"
import GettingStarted from "./GettingStarted"
import TodaysOutfit from "./TodaysOutfit"
import WardrobeInsights from "./WardrobeInsights"

const QUICK_ACTIONS: { label: string; hint: string; page: Page; icon: string }[] = [
  { label: "Build an outfit", hint: "From the clothes you own", page: "outfit-builder", icon: "✦" },
  { label: "Ask the AI Stylist", hint: "What should I wear?", page: "ai-stylist", icon: "◆" },
  { label: "Plan a trip", hint: "Pack with what you own", page: "help-me-pack", icon: "◈" },
  { label: "Check a purchase", hint: "Do I really need it?", page: "should-i-buy", icon: "◇" },
]

function greeting(hour: number) {
  if (hour < 12) return "Good morning"
  if (hour < 18) return "Good afternoon"
  return "Good evening"
}

export default function DashboardPage({ onNavigate }: { onNavigate: (page: Page) => void }) {
  const { items, health, loading, error } = useWardrobe()
  const { profile } = useUserData()
  const { user } = useAuth()
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
    const groups = TAXONOMY.groups.filter((group) => items.some((item) => item.category_group === group)).length
    const colors = new Set(items.map((item) => item.color_name).filter(Boolean)).size
    return {
      groups,
      colors,
      avgConfidence: items.length
        ? items.reduce((sum, item) => sum + (item.confidence ?? 0), 0) / items.length
        : 0,
      toReview: items.filter((item) => item.needs_review).length,
      confirmed: items.filter((item) => item.status === "confirmed").length,
    }
  }, [items])

  const displayName = profile?.display_name?.trim().split(/\s+/)[0] ?? ""
  const now = new Date()
  const dateLabel = now.toLocaleDateString("en", { weekday: "long", month: "long", day: "numeric" })

  return (
    <div className="space-y-6">
      <section className="relative overflow-hidden rounded-3xl bg-[#1C1C1C] p-8 text-white">
        <div className="pointer-events-none absolute -right-16 -top-20 h-72 w-72 rounded-full bg-[#556B2F]/30 blur-3xl" />
        <div className="relative flex flex-wrap items-center justify-between gap-6">
          <div className="flex items-center gap-5">
            <OwnAvatar
              initial={userInitial(profile?.display_name, user?.email)}
              size={72}
              className="ring-2 ring-[#556B2F]/60"
            />
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#8FAE5A]">{dateLabel}</p>
              <h1 className="mt-1 font-display text-3xl font-semibold">
                {greeting(now.getHours())}
                {displayName ? `, ${displayName}` : ""}.
              </h1>
              <p className="mt-1 text-sm text-white/55">
                {items.length
                  ? `You have ${items.length} piece${items.length === 1 ? "" : "s"} ready to style.`
                  : "Let's build your wardrobe: add your first piece."}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => onNavigate("outfit-builder")}
              className="rounded-lg bg-[#556B2F] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#6B8A3A]"
            >
              Build an outfit
            </button>
            <button
              type="button"
              onClick={() => onNavigate("wardrobe")}
              className="rounded-lg border border-white/25 px-5 py-2.5 text-sm font-semibold text-white hover:bg-white/10"
            >
              My wardrobe
            </button>
          </div>
        </div>

        <div className="relative mt-7 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { label: "Pieces", value: String(items.length) },
            { label: "Categories", value: `${stats.groups}/${TAXONOMY.groups.length}` },
            { label: "Colours", value: String(stats.colors) },
            { label: "To review", value: String(stats.toReview) },
          ].map((stat) => (
            <div key={stat.label} className="rounded-xl bg-white/[0.07] px-4 py-3">
              <p className="font-display text-2xl font-semibold">{stat.value}</p>
              <p className="text-[11px] uppercase tracking-widest text-white/45">{stat.label}</p>
            </div>
          ))}
        </div>
      </section>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {loading && !items.length ? (
        <div className="flex min-h-[240px] items-center justify-center text-sm text-[#8C8A82]">
          Loading your wardrobe...
        </div>
      ) : (
        <>
          <GettingStarted onNavigate={onNavigate} />

          <div className="grid gap-6 xl:grid-cols-[1fr_280px]">
            <TodaysOutfit onNavigate={onNavigate} />
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1 xl:content-start">
              {QUICK_ACTIONS.map((action) => (
                <button
                  key={action.page}
                  type="button"
                  onClick={() => onNavigate(action.page)}
                  className="flex items-center gap-3 rounded-2xl border border-[#E2E0D8] bg-white px-4 py-3.5 text-left transition-colors hover:border-[#556B2F]"
                >
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#E8EDE0] text-[#556B2F]">
                    {action.icon}
                  </span>
                  <span>
                    <span className="block text-sm font-semibold text-[#1C1C1C]">{action.label}</span>
                    <span className="block text-xs text-[#8C8A82]">{action.hint}</span>
                  </span>
                </button>
              ))}
            </div>
          </div>

          <OutfitsToBuy onOpenAvatar={() => onNavigate("avatar")} />

          <GapsCard onOpen={() => onNavigate("wardrobe-gaps")} />

          <WardrobeInsights />

          <details className="rounded-2xl border border-[#E2E0D8] bg-white p-6">
            <summary className="cursor-pointer list-none font-display text-base font-medium text-[#1C1C1C]">
              Model details
              <span className="ml-2 text-xs font-normal text-[#8C8A82]">how reliable the automatic detection is</span>
            </summary>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <div className="rounded-lg bg-[#F0EFEA] p-4">
                <p className="text-xs uppercase tracking-widest text-[#8C8A82]">Average confidence</p>
                <p className="mt-1 font-display text-2xl font-semibold text-[#1C1C1C]">
                  {Math.round(stats.avgConfidence * 100)}%
                </p>
              </div>
              <div className="rounded-lg bg-[#F0EFEA] p-4">
                <p className="text-xs uppercase tracking-widest text-[#8C8A82]">AI classification</p>
                <p className="mt-1 font-display text-2xl font-semibold text-[#1C1C1C]">{health?.llm ? "On" : "Off"}</p>
                <p className="text-xs text-[#8C8A82]">{health?.llm ? health.llm_model ?? "LLM ready" : "rules only"}</p>
              </div>
            </div>
            <div className="mt-5">
              <h2 className="font-display text-base font-medium text-[#1C1C1C]">Detection accuracy</h2>
              <p className="mb-4 mt-1 text-xs text-[#8C8A82]">
                Measured on items you reviewed. A field counts as wrong when you corrected it.
              </p>
              {accuracy.length ? (
                <div className="overflow-hidden rounded-lg border border-[#E2E0D8]">
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
                          <td className="px-3 py-2 text-[#1C1C1C]">{cap(row.field.replace(/_/g, " "))}</td>
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
                <p className="text-sm text-[#8C8A82]">Review and confirm a few items to see real accuracy numbers.</p>
              )}
              <p className="mt-3 text-xs text-[#8C8A82]">
                {stats.confirmed} item{stats.confirmed === 1 ? "" : "s"} confirmed so far.
              </p>
            </div>
          </details>
        </>
      )}
    </div>
  )
}
