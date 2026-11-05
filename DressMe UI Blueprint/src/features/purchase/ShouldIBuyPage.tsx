import { useEffect, useMemo, useRef, useState, type DragEvent } from "react"
import { api, asset } from "../../lib/api"
import { cap, seasonLabel } from "../../lib/taxonomy"
import type { PurchaseEvaluationResult, WardrobeItem } from "../../lib/types"
import { useWardrobe } from "../wardrobe/WardrobeProvider"

const VERDICT_THEME: Record<string, { bg: string; text: string; badge: string; label: string }> = {
  BUY: {
    bg: "bg-[#E8EDE0] border-[#556B2F]/30",
    text: "text-[#556B2F]",
    badge: "bg-[#556B2F] text-white",
    label: "Yes, buy it",
  },
  CONSIDER: {
    bg: "bg-amber-50 border-amber-200",
    text: "text-amber-800",
    badge: "bg-amber-600 text-white",
    label: "Think twice",
  },
  SKIP: {
    bg: "bg-red-50 border-red-200",
    text: "text-red-700",
    badge: "bg-red-600 text-white",
    label: "Skip this one",
  },
}

// One piece of a possible outfit: its picture (or its name when there is none) and a caption.
function OutfitTile({ image, label, highlight = false }: { image: string; label: string; highlight?: boolean }) {
  return (
    <div className="w-24 text-center">
      <div
        className={`flex aspect-[4/5] items-center justify-center overflow-hidden rounded-lg bg-white ${
          highlight ? "border-2 border-[#556B2F]" : "border border-[#E2E0D8]"
        }`}
      >
        {image ? (
          <img src={image} alt={label} className="h-full w-full object-contain p-1" />
        ) : (
          <span className="px-1 text-[10px] leading-tight text-[#8C8A82]">{label}</span>
        )}
      </div>
      <p className={`mt-1 line-clamp-2 text-[11px] leading-tight ${highlight ? "font-semibold text-[#556B2F]" : "text-[#1C1C1C]"}`}>
        {label}
      </p>
    </div>
  )
}

// The zones of the stylist's answer, in order. The backend sends the text; these titles are the page's.
const SECTION_TITLES = [
  ["verdict", "Our answer"],
  ["why_it_works", "Why"],
  ["final_advice", "Tip"],
] as const

type Tone = "good" | "warn" | "neutral"

// One plain-language proof: a short label, a big word, and one sentence.
function EvidenceCard({ label, value, detail, tone }: { label: string; value: string; detail: string; tone: Tone }) {
  const color = tone === "good" ? "text-[#556B2F]" : tone === "warn" ? "text-amber-700" : "text-[#1C1C1C]"
  return (
    <div className="rounded-xl border border-[#E2E0D8] bg-[#FAF9F6] p-3.5">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-[#8C8A82]">{label}</p>
      <p className={`mt-1 font-display text-lg font-semibold leading-tight ${color}`}>{value}</p>
      <p className="mt-1 text-xs leading-snug text-[#1C1C1C]/80">{detail}</p>
    </div>
  )
}

export default function ShouldIBuyPage() {
  const { items, health, addItems } = useWardrobe()

  const [file, setFile] = useState<File | null>(null)
  const [imageUrl, setImageUrl] = useState("")
  const [preview, setPreview] = useState("")
  const [prompt, setPrompt] = useState("")
  const [price, setPrice] = useState("")
  const [budget, setBudget] = useState("")

  const [busy, setBusy] = useState(false)
  const [addBusy, setAddBusy] = useState(false)
  const [error, setError] = useState("")
  const [added, setAdded] = useState(false)
  const [dragging, setDragging] = useState(false)

  const [evalResult, setEvalResult] = useState<PurchaseEvaluationResult | null>(null)
  const [analysis, setAnalysis] = useState<WardrobeItem | null>(null)

  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    return () => {
      if (preview && preview.startsWith("blob:")) URL.revokeObjectURL(preview)
    }
  }, [preview])

  const reset = () => {
    if (preview && preview.startsWith("blob:")) URL.revokeObjectURL(preview)
    setFile(null)
    setImageUrl("")
    setPreview("")
    setPrompt("")
    setPrice("")
    setBudget("")
    setEvalResult(null)
    setAnalysis(null)
    setError("")
    setAdded(false)
  }

  const handleFileSelect = (selected: File) => {
    if (!selected.type.startsWith("image/")) return
    if (preview && preview.startsWith("blob:")) URL.revokeObjectURL(preview)
    setFile(selected)
    setImageUrl("")
    setPreview(URL.createObjectURL(selected))
    setError("")
    setEvalResult(null)
  }

  const handleUrlChange = (url: string) => {
    if (file && preview && preview.startsWith("blob:")) URL.revokeObjectURL(preview)
    setFile(null)
    setImageUrl(url)
    setPreview(url.trim())
    setError("")
    setEvalResult(null)
  }

  const runEvaluation = async () => {
    if (!file && !imageUrl.trim()) {
      setError("Please attach a photo or paste an image link first.")
      return
    }

    setBusy(true)
    setError("")
    setEvalResult(null)

    try {
      // 1. Run the full intelligent purchasing evaluation
      const result = await api.evaluatePurchase({
        file,
        imageUrl: imageUrl.trim() || undefined,
        prompt: prompt.trim() || "Should I buy this?",
        price: parseFloat(price) || 0,
        budget: parseFloat(budget) || 0,
      })
      setEvalResult(result)

      // 2. If a local file was provided, also get detection preview for quick wardrobe add
      if (file) {
        api.analyze(file, { save: false }).then((res) => {
          if (res.items[0]) setAnalysis(res.items[0])
        }).catch(() => {})
      }
    } catch (evalError) {
      setError(
        evalError instanceof Error ? evalError.message : "Could not complete purchase evaluation.",
      )
    } finally {
      setBusy(false)
    }
  }

  const addToWardrobe = async () => {
    if (!file) return
    setAddBusy(true)
    setError("")
    try {
      const response = await api.analyze(file, { save: true })
      addItems(response.items)
      setAdded(true)
    } catch (addError) {
      setError(addError instanceof Error ? addError.message : "Could not add this item.")
    } finally {
      setAddBusy(false)
    }
  }

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    const selected = event.dataTransfer.files?.[0]
    if (selected && selected.type.startsWith("image/")) handleFileSelect(selected)
  }

  const verdict = evalResult?.agent_verdict?.decision?.toUpperCase() || ""
  const verdictTheme = VERDICT_THEME[verdict] || VERDICT_THEME.CONSIDER
  const toolEvidence = evalResult?.tool_evidence
  const candidate = evalResult?.candidate_item
  const detected = evalResult?.detected_item
  const itemName = detected?.name || candidate?.name || ""
  const closest = toolEvidence?.closest_wardrobe_match
  const redundancy = toolEvidence?.redundancy_score ?? 0
  const gap = toolEvidence?.wardrobe_gap_score ?? 0
  const outfitCount = toolEvidence?.compatible_outfits_count ?? 0
  const evidence: { label: string; value: string; detail: string; tone: Tone }[] = toolEvidence
    ? [
        redundancy >= 70
          ? { label: "In your closet", value: "Already owned", tone: "warn" as const,
              detail: closest ? `You own something very close: ${closest}.` : "You own something very close." }
          : redundancy >= 40
            ? { label: "In your closet", value: "Similar", tone: "neutral" as const,
                detail: closest ? `Close to your ${closest}.` : "Close to something you own." }
            : { label: "In your closet", value: "Something new", tone: "good" as const,
                detail: "Nothing like it in your closet yet." },
        gap >= 60
          ? { label: "Your wardrobe", value: "Fills a gap", tone: "good" as const, detail: "It adds something you are missing." }
          : gap >= 30
            ? { label: "Your wardrobe", value: "Adds a little", tone: "neutral" as const, detail: "Useful, but not a missing piece." }
            : { label: "Your wardrobe", value: "No real gap", tone: "warn" as const, detail: "Your wardrobe already covers this." },
        outfitCount > 0
          ? { label: "Outfits", value: `${outfitCount} outfit${outfitCount === 1 ? "" : "s"}`, tone: "good" as const,
              detail: "You can make with pieces you already own." }
          : { label: "Outfits", value: "Hard to match", tone: "warn" as const, detail: "Few of your pieces go with it." },
        ...(candidate?.within_budget != null
          ? [candidate.within_budget
              ? { label: "Price", value: "Within budget", tone: "good" as const,
                  detail: candidate.cost_per_outfit != null ? `About ${candidate.cost_per_outfit} per outfit.` : "It fits your budget." }
              : { label: "Price", value: "Over budget", tone: "warn" as const, detail: "It costs more than you planned." }]
          : []),
      ]
    : []
  const sections = SECTION_TITLES.flatMap(([key, title]) => {
    const lines = evalResult?.stylist_sections?.[key] ?? []
    return lines.length ? [{ key, title, lines }] : []
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Should I Buy?</h1>
        <p className="mt-1 text-sm text-[#8C8A82]">
          Thinking of buying a new piece? Upload a photo or paste a link, set your budget, and get an AI verdict grounded in your wardrobe.
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[440px_1fr]">
        {/* Left column: Inputs */}
        <div className="space-y-5 rounded-2xl border border-[#E2E0D8] bg-white p-6 shadow-sm">
          <div>
            <label className="text-xs font-semibold uppercase tracking-wider text-[#8C8A82]">
              Item Photo
            </label>

            {!preview ? (
              <div
                onClick={() => inputRef.current?.click()}
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragging(true)
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                className={`mt-2 flex min-h-[160px] cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 text-center transition-colors ${
                  dragging
                    ? "border-[#556B2F] bg-[#E8EDE0]"
                    : "border-[#E2E0D8] bg-[#FAF9F6] hover:border-[#556B2F]"
                }`}
              >
                <div className="mb-2 text-2xl text-[#556B2F]">📎</div>
                <p className="text-sm font-medium text-[#1C1C1C]">Drop an image here or browse</p>
                <p className="mt-1 text-xs text-[#8C8A82]">JPG, PNG, WEBP from your PC</p>
              </div>
            ) : (
              <div className="relative mt-2 overflow-hidden rounded-xl border border-[#E2E0D8] bg-[#FAF9F6]">
                <img
                  src={preview}
                  alt="Candidate preview"
                  className="max-h-[240px] w-full object-contain p-2"
                />
                <button
                  type="button"
                  onClick={reset}
                  className="absolute right-2 top-2 rounded-full bg-[#1C1C1C]/70 px-2 py-1 text-xs text-white hover:bg-[#1C1C1C]"
                >
                  ✕ Change
                </button>
              </div>
            )}

            {!file && (
              <div className="mt-3">
                <div className="flex items-center gap-2 text-xs text-[#8C8A82]">
                  <span className="h-px flex-1 bg-[#E2E0D8]" />
                  <span>or paste a link</span>
                  <span className="h-px flex-1 bg-[#E2E0D8]" />
                </div>
                <input
                  type="url"
                  placeholder="https://example.com/item.jpg"
                  value={imageUrl}
                  onChange={(e) => handleUrlChange(e.target.value)}
                  className="mt-2 w-full rounded-xl border border-[#E2E0D8] bg-[#FAF9F6] px-3.5 py-2.5 text-sm text-[#1C1C1C] outline-none transition-colors focus:border-[#556B2F]"
                />
              </div>
            )}

            <input
              ref={inputRef}
              type="file"
              accept="image/*"
              hidden
              onChange={(e) => {
                const selected = e.target.files?.[0]
                if (selected) handleFileSelect(selected)
                e.target.value = ""
              }}
            />
          </div>

          <div>
            <label className="text-xs font-semibold uppercase tracking-wider text-[#8C8A82]">
              Your Question / Prompt
            </label>
            <textarea
              rows={3}
              placeholder="e.g. Should I buy this for casual weekend wear? Does it work with my pants?"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              className="mt-2 w-full rounded-xl border border-[#E2E0D8] bg-[#FAF9F6] p-3 text-sm text-[#1C1C1C] outline-none transition-colors focus:border-[#556B2F]"
            />
          </div>

          <div>
            <label className="text-xs font-semibold uppercase tracking-wider text-[#8C8A82]">
              Budget & Pricing
            </label>
            <div className="mt-2 grid grid-cols-2 gap-3">
              <div>
                <span className="text-xs text-[#8C8A82]">Item Price</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="35.00"
                  value={price}
                  onChange={(e) => setPrice(e.target.value)}
                  className="mt-1 w-full rounded-xl border border-[#E2E0D8] bg-[#FAF9F6] px-3 py-2 text-sm text-[#1C1C1C] outline-none transition-colors focus:border-[#556B2F]"
                />
              </div>
              <div>
                <span className="text-xs text-[#8C8A82]">My Budget</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="50.00"
                  value={budget}
                  onChange={(e) => setBudget(e.target.value)}
                  className="mt-1 w-full rounded-xl border border-[#E2E0D8] bg-[#FAF9F6] px-3 py-2 text-sm text-[#1C1C1C] outline-none transition-colors focus:border-[#556B2F]"
                />
              </div>
            </div>
          </div>

          <button
            type="button"
            disabled={busy || (!file && !imageUrl.trim())}
            onClick={() => void runEvaluation()}
            className="w-full rounded-xl bg-[#556B2F] py-3.5 text-sm font-semibold text-white transition-colors hover:bg-[#6B8A3A] disabled:cursor-not-allowed disabled:opacity-45"
          >
            {busy ? "Analysing Item & Wardrobe..." : "Should I buy this?"}
          </button>
        </div>

        {/* Right column: Results */}
        <div className="space-y-5">
          {!evalResult && !busy && (
            <div className="flex min-h-[380px] flex-col items-center justify-center rounded-2xl border border-[#E2E0D8] bg-[#FAF9F6] p-10 text-center text-[#8C8A82]">
              <p className="font-medium text-[#1C1C1C]">Ready for evaluation</p>
              <p className="mt-1 max-w-sm text-sm">
                Attach an item image on the left, set your optional prompt and budget, then click "Should I buy this?" to see if it fills a wardrobe gap.
              </p>
            </div>
          )}

          {busy && (
            <div className="flex min-h-[380px] flex-col items-center justify-center rounded-2xl border border-[#E2E0D8] bg-[#FAF9F6] p-10 text-center">
              <div className="h-10 w-10 animate-spin rounded-full border-4 border-[#E2E0D8] border-t-[#556B2F]" />
              <p className="mt-4 text-sm font-medium text-[#1C1C1C]">
                Running Computer Vision & Wardrobe Match...
              </p>
              <p className="mt-1 text-xs text-[#8C8A82]">
                Evaluating colour harmony, redundancy risk, and outfit pairings
              </p>
            </div>
          )}

          {evalResult && (
            <div className="space-y-5 rounded-2xl border border-[#E2E0D8] bg-white p-6 shadow-sm">
              {/* 1. The answer at a glance */}
              <div className={`flex flex-wrap items-center justify-between gap-4 rounded-xl border p-4 ${verdictTheme.bg}`}>
                <div>
                  <p className={`text-xs font-bold uppercase tracking-wider ${verdictTheme.text}`}>Our answer</p>
                  <h2 className="mt-1 font-display text-3xl font-bold text-[#1C1C1C]">{verdictTheme.label}</h2>
                </div>
                {evalResult.agent_verdict?.score != null && (
                  <div className="text-right">
                    <span className="font-display text-3xl font-bold text-[#1C1C1C]">
                      {Math.round(evalResult.agent_verdict.score)}
                    </span>
                    <span className="text-sm font-medium text-[#8C8A82]">/100</span>
                    <p className="text-xs text-[#8C8A82]">Match score</p>
                  </div>
                )}
              </div>

              {/* 2. What we recognised: the shopper can check we understood the item */}
              {(itemName || candidate) && (
                <div className="flex items-center gap-3 rounded-xl border border-[#E2E0D8] bg-[#FAF9F6] p-3">
                  {preview && <img src={preview} alt="" className="h-16 w-14 shrink-0 rounded-lg bg-white object-contain" />}
                  <div className="min-w-0">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-[#8C8A82]">We see</p>
                    <p className="truncate text-sm font-semibold text-[#1C1C1C]">{itemName || cap(candidate?.detected_category ?? "")}</p>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {[detected?.category ?? candidate?.detected_category, detected?.color_name ?? candidate?.detected_color, detected?.material]
                        .filter((value): value is string => Boolean(value))
                        .map((value) => (
                          <span key={value} className="rounded-full bg-white px-2 py-0.5 text-[11px] text-[#1C1C1C] ring-1 ring-[#E2E0D8]">
                            {cap(value)}
                          </span>
                        ))}
                    </div>
                  </div>
                </div>
              )}

              {/* 3. The proof, in plain words */}
              {evidence.length > 0 && (
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  {evidence.map((card) => (
                    <EvidenceCard key={card.label} {...card} />
                  ))}
                </div>
              )}

              {/* 4. The explanation: one zone per section, the title written by the page in bold */}
              {sections.length > 0 ? (
                <div className="grid gap-3 md:grid-cols-2">
                  {sections.map((section) => (
                    <div
                      key={section.key}
                      className={`rounded-xl border p-4 ${
                        section.key === "verdict"
                          ? "border-[#556B2F]/40 bg-[#E8EDE0] md:col-span-2"
                          : "border-[#E2E0D8] bg-[#FAF9F6]"
                      }`}
                    >
                      <p className="text-sm font-bold text-[#1C1C1C]">{section.title}</p>
                      {section.lines.length === 1 ? (
                        <p className={`mt-2 leading-relaxed text-[#1C1C1C] ${section.key === "verdict" ? "text-base font-medium" : "text-sm"}`}>
                          {section.lines[0]}
                        </p>
                      ) : (
                        <ul className="mt-2 space-y-1.5">
                          {section.lines.map((line, index) => (
                            <li key={index} className="flex items-start gap-2 text-sm leading-relaxed text-[#1C1C1C]">
                              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#556B2F]" />
                              <span>{line}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                evalResult.stylist_interpretation && (
                  <div className="rounded-xl border border-[#E2E0D8] bg-[#FAF9F6] p-4">
                    <p className="text-sm font-bold text-[#1C1C1C]">Our answer</p>
                    <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-[#1C1C1C]">
                      {evalResult.stylist_interpretation}
                    </p>
                  </div>
                )
              )}

              {/* 5. What to wear it with: the pieces are shown as pictures, with the new piece first */}
              {toolEvidence?.matching_outfits && toolEvidence.matching_outfits.length > 0 && (
                <div>
                  <p className="text-sm font-bold text-[#1C1C1C]">Wear it with what you own</p>
                  <div className="mt-2 space-y-3">
                    {toolEvidence.matching_outfits.map((combo, idx) => (
                      <div key={idx} className="rounded-xl border border-[#E2E0D8] bg-[#FAF9F6] p-3">
                        <div className="flex items-center justify-between text-xs font-semibold text-[#556B2F]">
                          <span>Outfit {idx + 1}</span>
                          {combo.compatibility_score != null && <span>{Math.round(combo.compatibility_score)}% match</span>}
                        </div>
                        <div className="mt-3 flex flex-wrap gap-3">
                          {preview && <OutfitTile image={preview} label="New piece" highlight />}
                          {(combo.paired_items ?? []).map((pi, pj) => {
                            const owned = items.find((entry) => entry.id === pi.item_id)
                            return (
                              <OutfitTile
                                key={pj}
                                image={owned?.cutout_url ? asset(owned.cutout_url) : ""}
                                label={owned?.name || pi.name || pi.category}
                              />
                            )
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 6. The numbers behind it, for whoever wants them */}
              <details className="rounded-xl border border-[#E2E0D8] bg-white p-3 text-xs text-[#8C8A82]">
                <summary className="cursor-pointer font-semibold text-[#1C1C1C]">See the details</summary>
                <ul className="mt-2 space-y-1">
                  <li>Overlap with your closet: {redundancy}%</li>
                  <li>Gap it fills: {gap.toFixed(0)}/100</li>
                  <li>Outfits it makes: {outfitCount}</li>
                  {toolEvidence?.xgboost_prediction && (
                    <li>
                      Model decision: {toolEvidence.xgboost_prediction}
                      {toolEvidence.xgboost_confidence != null && ` (${Math.round(toolEvidence.xgboost_confidence * 100)}% confidence)`}
                    </li>
                  )}
                  {(evalResult.agent_verdict?.reasons ?? []).map((reason, i) => (
                    <li key={i}>{reason}</li>
                  ))}
                </ul>
              </details>

              {/* 7. Act on it */}
              {file && (
                <div className="pt-1">
                  <button
                    type="button"
                    disabled={addBusy || added}
                    onClick={() => void addToWardrobe()}
                    className="rounded-lg bg-[#1C1C1C] px-5 py-2.5 text-xs font-semibold text-white transition-colors hover:bg-black disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {added ? "Added to my wardrobe" : addBusy ? "Adding..." : "I bought it: add it to my wardrobe"}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
