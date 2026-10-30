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
    label: "Recommended: Buy It",
  },
  CONSIDER: {
    bg: "bg-amber-50 border-amber-200",
    text: "text-amber-800",
    badge: "bg-amber-600 text-white",
    label: "Consider With Care",
  },
  SKIP: {
    bg: "bg-red-50 border-red-200",
    text: "text-red-700",
    badge: "bg-red-600 text-white",
    label: "Skip / Don't Buy",
  },
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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Fashion Assistant</h1>
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
                <span className="text-xs text-[#8C8A82]">Item Price ($)</span>
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
                <span className="text-xs text-[#8C8A82]">My Budget ($)</span>
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
            {busy ? "Analysing Item & Wardrobe..." : "✦ Evaluate With Fashion Assistant"}
          </button>
        </div>

        {/* Right column: Results */}
        <div className="space-y-5">
          {!evalResult && !busy && (
            <div className="flex min-h-[380px] flex-col items-center justify-center rounded-2xl border border-[#E2E0D8] bg-[#FAF9F6] p-10 text-center text-[#8C8A82]">
              <span className="text-4xl">🛍️</span>
              <p className="mt-3 font-medium text-[#1C1C1C]">Ready for evaluation</p>
              <p className="mt-1 max-w-sm text-sm">
                Attach an item image on the left, set your optional prompt and budget, then click Evaluate to see if it fills a wardrobe gap.
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
              {/* Verdict banner */}
              <div className={`flex flex-wrap items-center justify-between gap-4 rounded-xl border p-4 ${verdictTheme.bg}`}>
                <div>
                  <span className={`inline-block rounded-md px-2.5 py-1 text-xs font-bold uppercase tracking-wider ${verdictTheme.badge}`}>
                    {verdict}
                  </span>
                  <h2 className="mt-1 font-display text-2xl font-bold text-[#1C1C1C]">
                    {verdictTheme.label}
                  </h2>
                </div>
                {evalResult.agent_verdict?.score != null && (
                  <div className="text-right">
                    <span className="font-display text-3xl font-bold text-[#1C1C1C]">
                      {Math.round(evalResult.agent_verdict.score)}
                    </span>
                    <span className="text-sm font-medium text-[#8C8A82]">/100</span>
                    <p className="text-xs text-[#8C8A82]">Suitability Score</p>
                  </div>
                )}
              </div>

              {/* Detected tags */}
              {candidate && (
                <div className="flex flex-wrap gap-2 text-xs">
                  {candidate.detected_category && (
                    <span className="rounded-full border border-[#E2E0D8] bg-[#FAF9F6] px-3 py-1 font-medium text-[#1C1C1C]">
                      Category: {cap(candidate.detected_category)}
                    </span>
                  )}
                  {candidate.detected_color && (
                    <span className="rounded-full border border-[#E2E0D8] bg-[#FAF9F6] px-3 py-1 font-medium text-[#1C1C1C]">
                      Colour: {cap(candidate.detected_color)}
                    </span>
                  )}
                  {candidate.inferred_occasion && (
                    <span className="rounded-full border border-[#E2E0D8] bg-[#FAF9F6] px-3 py-1 font-medium text-[#1C1C1C]">
                      Occasion: {candidate.inferred_occasion.replace("_", " ")}
                    </span>
                  )}
                </div>
              )}

              {/* Personal Stylist Interpretation */}
              {evalResult.stylist_interpretation && (
                <div className="rounded-xl border border-[#E2E0D8] bg-[#FAF9F6] p-4">
                  <p className="text-xs font-semibold uppercase tracking-wider text-[#556B2F]">
                    Personal Stylist Verdict
                  </p>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-[#1C1C1C]">
                    {evalResult.stylist_interpretation}
                  </p>
                </div>
              )}

              {/* Metrics */}
              {toolEvidence && (
                <div className="space-y-3 rounded-xl border border-[#E2E0D8] bg-[#FAF9F6] p-4">
                  <p className="text-xs font-semibold uppercase tracking-wider text-[#8C8A82]">
                    Key Signals
                  </p>

                  <div className="grid gap-3 text-sm sm:grid-cols-3">
                    <div>
                      <div className="flex justify-between text-xs text-[#8C8A82]">
                        <span>Redundancy Risk</span>
                        <span className="font-semibold text-[#1C1C1C]">{toolEvidence.redundancy_score ?? 0}%</span>
                      </div>
                      <div className="mt-1 h-2 overflow-hidden rounded-full bg-[#E2E0D8]">
                        <div
                          className={`h-full rounded-full transition-all ${
                            (toolEvidence.redundancy_score || 0) > 60 ? "bg-amber-600" : "bg-[#556B2F]"
                          }`}
                          style={{ width: `${Math.min(100, toolEvidence.redundancy_score || 0)}%` }}
                        />
                      </div>
                    </div>

                    <div>
                      <div className="flex justify-between text-xs text-[#8C8A82]">
                        <span>Wardrobe Gap Fill</span>
                        <span className="font-semibold text-[#1C1C1C]">
                          {toolEvidence.wardrobe_gap_score?.toFixed(0) ?? 0}/100
                        </span>
                      </div>
                      <div className="mt-1 h-2 overflow-hidden rounded-full bg-[#E2E0D8]">
                        <div
                          className="h-full rounded-full bg-[#556B2F] transition-all"
                          style={{ width: `${Math.min(100, toolEvidence.wardrobe_gap_score || 0)}%` }}
                        />
                      </div>
                    </div>

                    <div>
                      <div className="flex justify-between text-xs text-[#8C8A82]">
                        <span>Outfit Pairings</span>
                        <span className="font-semibold text-[#1C1C1C]">
                          {toolEvidence.compatible_outfits_count ?? 0} found
                        </span>
                      </div>
                      <div className="mt-1 h-2 overflow-hidden rounded-full bg-[#E2E0D8]">
                        <div
                          className="h-full rounded-full bg-[#556B2F] transition-all"
                          style={{
                            width: `${Math.min(100, (toolEvidence.compatible_outfits_count || 0) * 20)}%`,
                          }}
                        />
                      </div>
                    </div>
                  </div>

                  {toolEvidence.closest_wardrobe_match && (
                    <div className="mt-2 text-xs text-[#8C8A82]">
                      Closest item in closet: <b className="text-[#1C1C1C]">{toolEvidence.closest_wardrobe_match}</b>
                    </div>
                  )}

                  {toolEvidence.xgboost_prediction && (
                    <div className="text-xs text-[#8C8A82]">
                      ML Model Decision: <b className="text-[#1C1C1C]">{toolEvidence.xgboost_prediction}</b>{" "}
                      {toolEvidence.xgboost_confidence != null && (
                        <span>({Math.round(toolEvidence.xgboost_confidence * 100)}% confidence)</span>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Reasons */}
              {evalResult.agent_verdict?.reasons && evalResult.agent_verdict.reasons.length > 0 && (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-[#8C8A82]">
                    Evaluation Breakdown
                  </p>
                  <ul className="mt-2 space-y-1 text-sm text-[#1C1C1C]">
                    {evalResult.agent_verdict.reasons.map((reason, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <span className="text-[#556B2F]">•</span>
                        <span>{reason}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Ready-to-wear outfit pairings */}
              {toolEvidence?.matching_outfits && toolEvidence.matching_outfits.length > 0 && (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-[#8C8A82]">
                    Compatible Outfits From Closet
                  </p>
                  <div className="mt-2 space-y-2">
                    {toolEvidence.matching_outfits.map((combo, idx) => (
                      <div key={idx} className="rounded-xl border border-[#E2E0D8] bg-[#FAF9F6] p-3 text-sm">
                        <div className="flex items-center justify-between text-xs text-[#556B2F] font-semibold">
                          <span>Outfit Combination #{idx + 1}</span>
                          {combo.compatibility_score && (
                            <span>{Math.round(combo.compatibility_score)}% match</span>
                          )}
                        </div>
                        <p className="mt-1 text-xs text-[#1C1C1C]">{combo.description}</p>
                        {combo.paired_items && combo.paired_items.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            {combo.paired_items.map((pi, pj) => (
                              <span
                                key={pj}
                                className="rounded-md border border-[#E2E0D8] bg-white px-2 py-0.5 text-[11px] text-[#1C1C1C]"
                              >
                                {pi.name || pi.category} ({pi.color})
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Add to wardrobe button if file uploaded */}
              {file && (
                <div className="pt-2">
                  <button
                    type="button"
                    disabled={addBusy || added}
                    onClick={() => void addToWardrobe()}
                    className="rounded-lg bg-[#1C1C1C] px-5 py-2.5 text-xs font-semibold text-white transition-colors hover:bg-black disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {added ? "✓ Added to wardrobe" : addBusy ? "Adding..." : "+ Decide to buy: Add to Wardrobe"}
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
