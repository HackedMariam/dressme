import { useRef, useState } from "react"
import { api, asset } from "../../lib/api"
import { cap, seasonLabel } from "../../lib/taxonomy"
import type { WardrobeItem } from "../../lib/types"
import { useWardrobe } from "../wardrobe/WardrobeProvider"

function ResultCard({ item, reason }: { item: WardrobeItem; reason?: string }) {
  return (
    <div className="overflow-hidden rounded-xl border border-[#E2E0D8] bg-white">
      <div className="flex aspect-[4/5] items-center justify-center overflow-hidden bg-[#F0EFEA]">
        {item.cutout_url ? (
          <img
            src={asset(item.cutout_url)}
            alt={item.name}
            loading="lazy"
            className="h-full w-full object-contain"
          />
        ) : null}
      </div>
      <div className="space-y-1 p-3">
        <p className="truncate text-sm font-semibold text-[#1C1C1C]">{item.name}</p>
        <p className="truncate text-[11px] text-[#8C8A82]">
          {cap(item.category)} - {cap(item.color_name ?? "unknown")} -{" "}
          {seasonLabel(item.seasons ?? [])}
        </p>
        {reason && (
          <span className="inline-block rounded-full bg-[#E8EDE0] px-2 py-0.5 text-[10px] font-semibold text-[#556B2F]">
            {reason}
          </span>
        )}
      </div>
    </div>
  )
}

export default function FindSimilarPage() {
  const { items } = useWardrobe()
  const [query, setQuery] = useState("")
  const [match, setMatch] = useState<WardrobeItem | null | undefined>(undefined)
  const [agentReply, setAgentReply] = useState("")
  const [agentItems, setAgentItems] = useState<WardrobeItem[]>([])
  const [busy, setBusy] = useState(false)
  const [mode, setMode] = useState<"photo" | "text" | null>(null)
  const [error, setError] = useState("")
  const fileInput = useRef<HTMLInputElement>(null)

  const reset = () => {
    setMatch(undefined)
    setAgentReply("")
    setAgentItems([])
    setError("")
    setMode(null)
  }

  const searchPhoto = async (file: File | undefined) => {
    if (!file) return
    reset()
    setMode("photo")
    setBusy(true)
    try {
      const response = await api.searchByPhoto(file)
      setMatch(response.match)
    } catch (searchError) {
      setError(
        searchError instanceof Error ? searchError.message : "Could not search by photo.",
      )
    } finally {
      setBusy(false)
    }
  }

  const searchText = async () => {
    const message = query.trim()
    if (!message) return
    reset()
    setMode("text")
    setBusy(true)
    try {
      const response = await api.agentSearch(message)
      setAgentReply(response.reply)
      setAgentItems(response.items)
    } catch (searchError) {
      setError(
        searchError instanceof Error ? searchError.message : "Could not search your wardrobe.",
      )
    } finally {
      setBusy(false)
    }
  }

  const related = match
    ? items
        .filter(
          (item) =>
            item.id !== match.id &&
            (item.category === match.category || item.category_group === match.category_group),
        )
        .slice(0, 6)
    : []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Find Similar</h1>
        <p className="mt-1 text-sm text-[#8C8A82]">
          Search your wardrobe with a photo or a plain-language description.
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <div className="space-y-4">
          <div className="rounded-xl border border-[#E2E0D8] bg-[#F0EFEA] p-5">
            <p className="text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
              By photo
            </p>
            <p className="mt-1 text-xs text-[#8C8A82]">
              Upload an item and find the closest match you already own.
            </p>
            <button
              type="button"
              disabled={busy}
              onClick={() => fileInput.current?.click()}
              className="mt-3 w-full rounded-lg bg-[#1C1C1C] px-3 py-2.5 text-xs font-semibold text-white transition-colors hover:bg-[#333] disabled:opacity-40"
            >
              {busy && mode === "photo" ? "Searching..." : "Choose a photo"}
            </button>
            <input
              ref={fileInput}
              type="file"
              accept="image/*"
              hidden
              onChange={(event) => {
                void searchPhoto(event.target.files?.[0])
                event.target.value = ""
              }}
            />
          </div>

          <div className="rounded-xl border border-[#E2E0D8] bg-white p-5">
            <p className="text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
              By description
            </p>
            <p className="mt-1 text-xs text-[#8C8A82]">
              For example: "something warm for a rainy work day".
            </p>
            <textarea
              rows={3}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault()
                  void searchText()
                }
              }}
              placeholder="Describe the item or occasion..."
              className="mt-3 w-full resize-y rounded-lg border border-[#E2E0D8] px-3 py-2 text-sm text-[#1C1C1C] outline-none focus:border-[#556B2F]"
            />
            <button
              type="button"
              disabled={busy || !query.trim()}
              onClick={() => void searchText()}
              className="mt-2 w-full rounded-lg bg-[#556B2F] px-3 py-2.5 text-xs font-semibold text-white transition-colors hover:bg-[#6B8A3A] disabled:opacity-40"
            >
              {busy && mode === "text" ? "Searching..." : "Search wardrobe"}
            </button>
          </div>

          <button
            type="button"
            onClick={reset}
            className="text-xs text-[#8C8A82] underline hover:text-[#1C1C1C]"
          >
            Clear results
          </button>
        </div>

        <div className="space-y-4">
          {busy && (
            <div className="flex min-h-[240px] items-center justify-center rounded-xl bg-[#F0EFEA] text-sm text-[#8C8A82]">
              Searching...
            </div>
          )}

          {!busy && mode === "photo" && (
            <>
              <p className="text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
                {match ? "Closest match" : "No match found"}
              </p>
              {match ? (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  <ResultCard item={match} reason="Best match" />
                  {related.map((item) => (
                    <ResultCard
                      key={item.id}
                      item={item}
                      reason={item.color_name === match.color_name ? "Same colour" : undefined}
                    />
                  ))}
                </div>
              ) : (
                <div className="rounded-xl border border-[#E2E0D8] bg-[#F0EFEA] px-6 py-10 text-center text-sm text-[#8C8A82]">
                  Nothing similar was found in your wardrobe.
                </div>
              )}
            </>
          )}

          {!busy && mode === "text" && (
            <>
              {agentReply && (
                <div className="rounded-xl bg-[#1C1C1C] p-5 text-sm leading-relaxed text-white">
                  <p className="text-xs font-semibold uppercase tracking-widest text-[#8FAE5A]">
                    Stylist
                  </p>
                  <p className="mt-2 text-white/80">{agentReply}</p>
                </div>
              )}
              <p className="text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
                {agentItems.length} matching item{agentItems.length === 1 ? "" : "s"}
              </p>
              {agentItems.length ? (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {agentItems.map((item) => (
                    <ResultCard key={item.id} item={item} />
                  ))}
                </div>
              ) : (
                <div className="rounded-xl border border-[#E2E0D8] bg-[#F0EFEA] px-6 py-10 text-center text-sm text-[#8C8A82]">
                  No items matched that description.
                </div>
              )}
            </>
          )}

          {!busy && !mode && (
            <div className="flex min-h-[320px] flex-col items-center justify-center rounded-xl border border-[#E2E0D8] bg-[#F0EFEA] px-8 text-center">
              <p className="font-medium text-[#1C1C1C]">Search your own wardrobe</p>
              <p className="mt-1 max-w-sm text-sm text-[#8C8A82]">
                Retail catalogue matching is not connected on this branch yet. These searches use
                the items stored in your Supabase wardrobe.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
