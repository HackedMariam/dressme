import { useEffect, useRef, useState } from "react"
import { api } from "../../lib/api"
import { cap } from "../../lib/taxonomy"
import type { AdviceSource, StylistSections, StylistWeather, WardrobeItem, WardrobePending } from "../../lib/types"
import StylistAnswer, { type OutfitCard } from "./StylistAnswer"
import type { Page } from "../shell/navigation"
import { useSpeech } from "../../lib/useSpeech"
import { useUserData } from "../profile/UserDataProvider"
import { parseLocation } from "../profile/types"
import { useWardrobe } from "../wardrobe/WardrobeProvider"

interface ChatMessage {
  id: string
  role: "user" | "assistant"
  text: string
  items?: WardrobeItem[]
  sources?: AdviceSource[]
  sections?: StylistSections | null
  weather?: StylistWeather | null
  agentLabel?: string
  agentsCalled?: string[]
  action?: { page: string; label: string } | null
  outfits?: OutfitCard[]
  pending?: WardrobePending | null
  error?: boolean
}

// Suggestions come from what the user really owns, so they always make sense for this wardrobe.
function quickPromptsFor(items: WardrobeItem[]) {
  const prompts = ["What should I wear to a dinner party?", "I have a job interview tomorrow"]
  const piece = items.find((item) => item.category_group === "Outerwear") ?? items.find((item) => item.cutout_url)
  if (piece) prompts.push(`How can I style my ${piece.name.toLowerCase()} differently?`)
  prompts.push("Which colours go well with navy?", "Build me a casual weekend look")
  return prompts
}

function createId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export default function StylistPage({ onNavigate }: { onNavigate?: (page: Page) => void }) {
  const { items, health, error: wardrobeError } = useWardrobe()
  const { profile, preferences } = useUserData()
  const [input, setInput] = useState("")
  const [busy, setBusy] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [error, setError] = useState("")
  const [threadId, setThreadId] = useState<string | undefined>()
  const scrollRef = useRef<HTMLDivElement>(null)
  const displayName = profile?.display_name?.trim() || "there"
  const place = parseLocation(profile?.location ?? null)

  useEffect(() => {
    const node = scrollRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [messages, busy])

  const send = async (raw?: string) => {
    const text = (raw ?? input).trim()
    if (!text || busy) return
    setInput("")
    setError("")
    setMessages((previous) => [
      ...previous,
      { id: createId(), role: "user", text },
    ])
    setBusy(true)
    try {
      // The orchestrator reads the request, picks the agent (stylist, wardrobe, outfits, trip, gaps) and remembers the thread.
      const response = await api.assistant(text, {
        threadId,
        city: place.city || "Tunis",
        country: place.country || "Tunisia",
        unit: profile?.temperature_unit ?? "Celsius",
      })
      setThreadId(response.thread_id)
      setMessages((previous) => [
        ...previous,
        {
          id: createId(),
          role: "assistant",
          text: response.reply,
          items: response.items.map((found) => items.find((owned) => owned.id === found.id) ?? found),
          sources: response.data.sources ?? [],
          sections: response.data.sections ?? null,
          weather: response.data.weather ?? null,
          agentLabel: response.agent_label,
          agentsCalled: response.agents_called,
          action: response.action,
          pending: response.data.pending ?? null,
          outfits: (response.data.outfits ?? []).map((outfit) => ({
            ...outfit,
            items: outfit.items
              .map((piece) => items.find((owned) => owned.id === piece.id))
              .filter((owned): owned is WardrobeItem => Boolean(owned)),
          })),
        },
      ])
    } catch (sendError) {
      const message =
        sendError instanceof Error ? sendError.message : "The stylist could not answer right now."
      setError(message)
      setMessages((previous) => [
        ...previous,
        {
          id: createId(),
          role: "assistant",
          text: message,
          error: true,
        },
      ])
    } finally {
      setBusy(false)
    }
  }

  const speech = useSpeech((text, final) => {
    setInput(text)
    if (final && text) void send(text)
  })

  const styles = preferences?.preferred_styles ?? []
  const colors = preferences?.preferred_colors ?? []

  return (
    <div className="flex h-full min-h-[560px] flex-col gap-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">AI Stylist</h1>
        <p className="mt-1 text-sm text-[#8C8A82]">
          One assistant, several agents: styling, wardrobe, outfits, trips and gaps, each answered by the right one
        </p>
        {!place.city && (
          <p className="mt-1 text-xs text-[#8C8A82]">
            Weather is taken for Tunis. Set your city in your profile to use yours.
          </p>
        )}
      </div>

      <div className="flex min-h-0 flex-1 gap-6">
        <div className="flex min-h-[520px] flex-1 flex-col overflow-hidden rounded-xl bg-[#F0EFEA]">
          <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-6">
            <div className="flex gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#556B2F] text-xs font-semibold text-white">
                AI
              </div>
              <div className="max-w-[80%] rounded-2xl rounded-tl-none bg-white px-4 py-3 text-sm leading-relaxed text-[#1C1C1C]">
                Hi {displayName}! I can see {items.length} item{items.length === 1 ? "" : "s"} in
                your wardrobe. Ask me what to wear, how to style a piece, or whether something is
                worth buying.
              </div>
            </div>

            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex gap-3 ${message.role === "user" ? "flex-row-reverse" : ""}`}
              >
                <div
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                    message.role === "assistant"
                      ? "bg-[#556B2F] text-white"
                      : "bg-[#1C1C1C] text-white"
                  }`}
                >
                  {message.role === "assistant" ? "AI" : "You"}
                </div>
                <div
                  className={`max-w-[88%] space-y-3 rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                    message.role === "assistant"
                      ? message.error
                        ? "rounded-tl-none bg-red-50 text-red-700"
                        : "rounded-tl-none bg-white text-[#1C1C1C]"
                      : "rounded-tr-none bg-[#1C1C1C] text-white"
                  }`}
                >
                  {message.role === "assistant" && !message.error ? (
                    <StylistAnswer
                      text={message.text}
                      sections={message.sections}
                      weather={message.weather}
                      items={message.items ?? []}
                      sources={message.sources ?? []}
                      outfits={message.outfits}
                    />
                  ) : (
                    <p className="whitespace-pre-line">{message.text}</p>
                  )}
                  {message.role === "assistant" && !message.error && message.agentLabel && (
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-[#8C8A82]">
                      Answered by {message.agentsCalled?.length ? message.agentsCalled.join(" + ") : message.agentLabel}
                    </p>
                  )}
                  {message.pending && (
                    <div className="space-y-2 rounded-lg border border-amber-300 bg-amber-50 p-3">
                      <p className="text-xs font-bold text-amber-900">Change proposed for {message.pending.item_name}</p>
                      <ul className="space-y-0.5 text-xs text-amber-900">
                        {Object.entries(message.pending.fields).map(([field, value]) => (
                          <li key={field}>
                            {field.replace(/_/g, " ")}: {String(message.pending?.before[field] ?? "-")} &rarr; <b>{String(value)}</b>
                          </li>
                        ))}
                      </ul>
                      <div className="flex gap-2">
                        <button type="button" disabled={busy} onClick={() => void send("yes")}
                          className="rounded-lg bg-[#1C1C1C] px-3 py-1.5 text-xs font-semibold text-white hover:bg-black disabled:opacity-40">
                          Confirm change
                        </button>
                        <button type="button" disabled={busy} onClick={() => void send("no")}
                          className="rounded-lg border border-[#E2E0D8] bg-white px-3 py-1.5 text-xs font-semibold text-[#1C1C1C] hover:bg-[#F0EFEA] disabled:opacity-40">
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                  {message.action && onNavigate && (
                    <button type="button" onClick={() => onNavigate(message.action!.page as Page)}
                      className="rounded-lg bg-[#556B2F] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[#6B8A3A]">
                      {message.action.label}
                    </button>
                  )}
                </div>
              </div>
            ))}

            {busy && (
              <div className="flex gap-3">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#556B2F] text-xs font-semibold text-white">
                  AI
                </div>
                <div className="rounded-2xl rounded-tl-none bg-white px-4 py-3 text-sm text-[#8C8A82]">
                  Searching your wardrobe...
                </div>
              </div>
            )}
          </div>

          <div className="flex flex-wrap gap-2 border-t border-[#E2E0D8] px-6 py-3">
            {quickPromptsFor(items).map((prompt) => (
              <button
                key={prompt}
                type="button"
                disabled={busy}
                onClick={() => void send(prompt)}
                className="rounded-full border border-[#E2E0D8] bg-white px-3 py-1.5 text-xs text-[#1C1C1C] transition-colors hover:border-[#556B2F] disabled:opacity-40"
              >
                {prompt}
              </button>
            ))}
          </div>

          <div className="flex gap-3 border-t border-[#E2E0D8] p-4">
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void send()
              }}
              placeholder="Ask your AI stylist about your wardrobe..."
              className="flex-1 rounded-xl border border-[#E2E0D8] bg-white px-4 py-2.5 text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F]"
            />
            {speech.supported && (
              <button
                type="button"
                title={speech.listening ? "Stop listening" : "Ask by voice"}
                aria-label="Ask by voice"
                onClick={speech.toggle}
                className={`rounded-xl border border-[#E2E0D8] px-3 transition-colors ${
                  speech.listening ? "animate-pulse bg-red-100 text-red-600" : "bg-white text-[#8C8A82] hover:bg-[#F0EFEA]"
                }`}
              >
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <rect x="9" y="3" width="6" height="11" rx="3" />
                  <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
                </svg>
              </button>
            )}
            <button
              type="button"
              disabled={busy || !input.trim()}
              onClick={() => void send()}
              className="rounded-xl bg-[#556B2F] px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#6B8A3A] disabled:opacity-40"
            >
              {busy ? "..." : "Send"}
            </button>
          </div>
        </div>

        <div className="hidden w-64 space-y-4 lg:block">
          <div className="rounded-xl bg-[#F0EFEA] p-5">
            <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
              Active context
            </p>
            {[
              { label: "Wardrobe items", value: String(items.length) },
              { label: "AI model", value: health?.llm ? health.llm_model ?? "Ready" : "Rules only" },
              {
                label: "Preferred styles",
                value: styles.length ? styles.slice(0, 2).map(cap).join(", ") : "Not set",
              },
              {
                label: "Preferred colours",
                value: colors.length ? colors.slice(0, 3).map(cap).join(", ") : "Not set",
              },
            ].map((entry) => (
              <div
                key={entry.label}
                className="flex justify-between gap-3 border-b border-[#E2E0D8] py-2 last:border-0"
              >
                <span className="text-xs text-[#8C8A82]">{entry.label}</span>
                <span className="text-right text-xs font-medium text-[#1C1C1C]">{entry.value}</span>
              </div>
            ))}
          </div>

          {(error || wardrobeError) && (
            <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-xs text-red-700">
              {error || wardrobeError}
            </div>
          )}

          <div className="rounded-xl border border-[#E2E0D8] bg-white p-4 text-xs text-[#8C8A82]">
            The stylist only recommends items it can find in your wardrobe. General style advice
            comes from a library of fashion books and is shown with its sources (like [S1]). If it
            cannot find a match, it will say so instead of inventing one.
          </div>
        </div>
      </div>
    </div>
  )
}
