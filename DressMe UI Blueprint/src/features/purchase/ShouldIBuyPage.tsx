import { useEffect, useMemo, useRef, useState, type DragEvent } from "react"
import { api, asset } from "../../lib/api"
import { cap, seasonLabel } from "../../lib/taxonomy"
import type { DuplicateResult, PurchaseEvaluation, WardrobeItem } from "../../lib/types"
import { useWardrobe } from "../wardrobe/WardrobeProvider"

const VERDICT_STYLE: Record<string, { bg: string; text: string; label: string }> = {
  BUY: { bg: "bg-[#E8EDE0]", text: "text-[#556B2F]", label: "Go for it" },
  CONSIDER: { bg: "bg-amber-100", text: "text-amber-800", label: "Think twice" },
  SKIP: { bg: "bg-red-100", text: "text-red-700", label: "Better skip" },
}

function Rich({ text }: { text: string }) {
  return (
    <div className="space-y-2 text-sm leading-relaxed text-[#1C1C1C]">
      {text.split(/\n+/).filter(Boolean).map((line, index) => (
        <p key={index}>
          {line.split(/\*\*(.+?)\*\*/g).map((part, i) =>
            i % 2 ? <b key={i}>{part}</b> : part,
          )}
        </p>
      ))}
    </div>
  )
}

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-[#E2E0D8] bg-white p-3">
      <p className="text-[10px] font-semibold uppercase tracking-widest text-[#8C8A82]">{label}</p>
      <p className="mt-1 text-lg font-semibold text-[#1C1C1C]">{value}</p>
      {hint && <p className="truncate text-[10px] text-[#8C8A82]">{hint}</p>}
    </div>
  )
}

function EvaluationCard({ evaluation, loading }: { evaluation: PurchaseEvaluation | null; loading: boolean }) {
  if (!evaluation) {
    return (
      <div className="rounded-xl bg-[#F0EFEA] p-5 text-sm text-[#8C8A82]">
        {loading ? "Evaluating this purchase..." : ""}
      </div>
    )
  }
  const { agent_verdict: verdict, tool_evidence: evidence, candidate_item: candidate } = evaluation
  const style = VERDICT_STYLE[verdict.decision.toUpperCase()] ?? VERDICT_STYLE.CONSIDER
  const score = Math.max(0, Math.min(100, verdict.score))
  const overBudget = candidate.price - candidate.budget
  return (
    <div className="space-y-4 rounded-xl bg-[#F0EFEA] p-5">
      <p className="text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">Purchase verdict</p>
      <div className={`rounded-xl ${style.bg} p-4`}>
        <div className="flex items-end justify-between">
          <div>
            <p className={`font-display text-3xl font-semibold ${style.text}`}>{verdict.decision}</p>
            <p className={`text-sm ${style.text}`}>{style.label}</p>
          </div>
          <p className="text-sm text-[#1C1C1C]"><b className="text-2xl">{score}</b>/100</p>
        </div>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/70">
          <div className="h-full rounded-full bg-[#556B2F]" style={{ width: `${score}%` }} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Metric
          label="Price vs budget"
          value={`${candidate.price} / ${candidate.budget}`}
          hint={overBudget > 0 ? `${overBudget} over budget (-${evidence.budget_penalty} pts)` : "Within budget"}
        />
        <Metric
          label="Redundancy"
          value={`${evidence.redundancy_score}%`}
          hint={evidence.closest_wardrobe_match ? `Closest: ${evidence.closest_wardrobe_match}` : "Nothing similar owned"}
        />
        <Metric label="Compatible outfits" value={String(evidence.compatible_outfits_count)} />
        <Metric label="Wardrobe gap filled" value={`${evidence.wardrobe_gap_score}/100`} />
      </div>

      <p className="text-xs text-[#8C8A82]">
        Detected: {cap(candidate.detected_color)} {cap(candidate.detected_category)} - {cap(candidate.inferred_occasion)}
      </p>

      {(evidence.matching_outfits ?? []).length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">Outfits it would complete</p>
          <div className="mt-2 space-y-2">
            {(evidence.matching_outfits ?? []).map((outfit) => (
              <div key={outfit.outfit_id} className="rounded-lg border border-[#E2E0D8] bg-white p-2.5">
                <p className="text-xs text-[#1C1C1C]">
                  {outfit.paired_items.map((piece) => piece.name).join(" + ")}
                </p>
                <p className="text-[10px] text-[#8C8A82]">Compatibility {outfit.compatibility_score}/100</p>
              </div>
            ))}
          </div>
        </div>
      )}

      <ul className="list-disc space-y-1 pl-5 text-xs text-[#1C1C1C]">
        {verdict.reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>

      {evaluation.stylist_interpretation && (
        <div className="rounded-lg border border-[#E2E0D8] bg-white p-4">
          <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
            Stylist interpretation
          </p>
          <Rich text={evaluation.stylist_interpretation} />
        </div>
      )}
    </div>
  )
}

export default function ShouldIBuyPage() {
  const { items, health, addItems } = useWardrobe()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState("")
  const [analysis, setAnalysis] = useState<WardrobeItem | null>(null)
  const [duplicate, setDuplicate] = useState<DuplicateResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [addBusy, setAddBusy] = useState(false)
  const [error, setError] = useState("")
  const [added, setAdded] = useState(false)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const [price, setPrice] = useState("")
  const [budget, setBudget] = useState("")
  const [question, setQuestion] = useState("")
  const [evaluation, setEvaluation] = useState<PurchaseEvaluation | null>(null)
  const [evaluating, setEvaluating] = useState(false)

  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview)
    }
  }, [preview])

  const similar = useMemo(() => {
    if (!analysis) return []
    return items
      .filter(
        (item) =>
          item.category === analysis.category ||
          item.category_group === analysis.category_group,
      )
      .sort((a, b) => {
        const aColor = a.color_name === analysis.color_name ? 1 : 0
        const bColor = b.color_name === analysis.color_name ? 1 : 0
        const aPattern = a.pattern === analysis.pattern ? 1 : 0
        const bPattern = b.pattern === analysis.pattern ? 1 : 0
        return bColor + bPattern - (aColor + aPattern)
      })
      .slice(0, 4)
  }, [analysis, items])

  const duplicateItem = duplicate?.similar_item_id
    ? items.find((item) => item.id === duplicate.similar_item_id) ?? null
    : null

  const reset = () => {
    setFile(null)
    setPreview("")
    setAnalysis(null)
    setDuplicate(null)
    setError("")
    setAdded(false)
    setEvaluation(null)
  }

  const evaluatePurchase = async () => {
    if (!file) return
    setEvaluating(true)
    setError("")
    try {
      setEvaluation(
        await api.evaluatePurchase(file, Number(price), Number(budget), question || "Should I buy this?"),
      )
    } catch (evalError) {
      setError(evalError instanceof Error ? evalError.message : "Could not evaluate this purchase.")
    } finally {
      setEvaluating(false)
    }
  }

  const analyzeFile = async (selected: File) => {
    reset()
    setFile(selected)
    const objectUrl = URL.createObjectURL(selected)
    setPreview(objectUrl)
    if (health && !health.model_loaded) {
      setError("The detection model is not loaded on the server, so this photo cannot be analysed.")
      return
    }
    setBusy(true)
    try {
      const response = await api.analyze(selected, { save: false })
      const detected = response.items[0] ?? null
      setAnalysis(detected)
      if (detected) {
        const result = await api.checkDuplicate(detected).catch(() => null)
        setDuplicate(result)
      }
    } catch (analysisError) {
      setError(
        analysisError instanceof Error ? analysisError.message : "Could not analyse this photo.",
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
    if (selected && selected.type.startsWith("image/")) void analyzeFile(selected)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-[#1C1C1C]">Should I Buy?</h1>
        <p className="mt-1 text-sm text-[#8C8A82]">
          Photograph an item you are considering. We compare it with what you already own.
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
        <div className="space-y-4">
          {!file ? (
            <div
              onClick={() => inputRef.current?.click()}
              onDragOver={(event) => {
                event.preventDefault()
                setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={`flex min-h-[320px] cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-8 text-center transition-colors ${
                dragging
                  ? "border-[#556B2F] bg-[#E8EDE0]"
                  : "border-[#E2E0D8] bg-[#F0EFEA] hover:border-[#556B2F]"
              }`}
            >
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-[#E2E0D8] text-2xl text-[#8C8A82]">
                +
              </div>
              <p className="font-medium text-[#1C1C1C]">Add a photo of the item</p>
              <p className="mt-1 text-sm text-[#8C8A82]">
                Use a clean photo of the garment, or upload a screenshot.
              </p>
              <button
                type="button"
                className="mt-4 rounded-lg bg-[#1C1C1C] px-5 py-2.5 text-sm font-semibold text-white"
              >
                Choose a photo
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="overflow-hidden rounded-xl border border-[#E2E0D8] bg-[#F0EFEA]">
                <div className="flex aspect-[4/3] items-center justify-center">
                  {busy && !analysis ? (
                    <p className="text-sm text-[#8C8A82]">Analysing the item...</p>
                  ) : (
                    <img
                      src={analysis?.cutout_url ? asset(analysis.cutout_url) : preview}
                      alt="Item being analysed"
                      className="h-full w-full object-contain"
                    />
                  )}
                </div>
              </div>

              {analysis && (
                <div className="rounded-xl bg-[#F0EFEA] p-5">
                  <p className="text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
                    Detected item
                  </p>
                  <h2 className="mt-1 font-display text-xl font-medium text-[#1C1C1C]">
                    {analysis.name}
                  </h2>
                  <div className="mt-3 flex flex-wrap gap-2 text-xs">
                    {[
                      cap(analysis.category),
                      cap(analysis.color_name ?? "unknown colour"),
                      cap(analysis.pattern ?? "no pattern"),
                      analysis.material ? cap(analysis.material) : null,
                      seasonLabel(analysis.seasons ?? []),
                    ]
                      .filter(Boolean)
                      .map((label) => (
                        <span
                          key={label}
                          className="rounded-full border border-[#E2E0D8] bg-white px-2.5 py-1 text-[#1C1C1C]"
                        >
                          {label}
                        </span>
                      ))}
                  </div>
                  {(analysis.occasions ?? []).length > 0 && (
                    <p className="mt-3 text-xs text-[#8C8A82]">
                      Occasions: {(analysis.occasions ?? []).map(cap).join(", ")}
                    </p>
                  )}

                  <div className="mt-4 flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={addBusy || added}
                      onClick={() => void addToWardrobe()}
                      className="rounded-lg bg-[#556B2F] px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#6B8A3A] disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {added ? "Added to wardrobe" : addBusy ? "Adding..." : "Add to wardrobe"}
                    </button>
                    <button
                      type="button"
                      onClick={reset}
                      className="rounded-lg border border-[#E2E0D8] bg-white px-4 py-2.5 text-sm font-semibold text-[#1C1C1C] transition-colors hover:bg-[#F0EFEA]"
                    >
                      Analyse another item
                    </button>
                  </div>
                </div>
              )}

              {analysis && (
                <div className="rounded-xl bg-[#F0EFEA] p-5">
                  <p className="text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
                    Purchase evaluation
                  </p>
                  <div className="mt-3 grid grid-cols-2 gap-3">
                    <label className="text-xs text-[#8C8A82]">
                      Price of the garment
                      <input
                        type="number"
                        min="0"
                        value={price}
                        onChange={(event) => setPrice(event.target.value)}
                        placeholder="e.g. 120"
                        className="mt-1 w-full rounded-lg border border-[#E2E0D8] bg-white px-3 py-2 text-sm text-[#1C1C1C]"
                      />
                    </label>
                    <label className="text-xs text-[#8C8A82]">
                      Your budget
                      <input
                        type="number"
                        min="0"
                        value={budget}
                        onChange={(event) => setBudget(event.target.value)}
                        placeholder="e.g. 100"
                        className="mt-1 w-full rounded-lg border border-[#E2E0D8] bg-white px-3 py-2 text-sm text-[#1C1C1C]"
                      />
                    </label>
                  </div>
                  <label className="mt-3 block text-xs text-[#8C8A82]">
                    Your question
                    <textarea
                      value={question}
                      onChange={(event) => setQuestion(event.target.value)}
                      rows={2}
                      placeholder="e.g. Is this blazer good for work?"
                      className="mt-1 w-full rounded-lg border border-[#E2E0D8] bg-white px-3 py-2 text-sm text-[#1C1C1C]"
                    />
                  </label>
                  <button
                    type="button"
                    disabled={evaluating || !(Number(price) > 0) || !(Number(budget) > 0)}
                    onClick={() => void evaluatePurchase()}
                    className="mt-3 rounded-lg bg-[#1C1C1C] px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {evaluating ? "Evaluating..." : "Should I buy it?"}
                  </button>
                </div>
              )}
            </div>
          )}

          <input
            ref={inputRef}
            type="file"
            accept="image/*"
            hidden
            onChange={(event) => {
              const selected = event.target.files?.[0]
              if (selected) void analyzeFile(selected)
              event.target.value = ""
            }}
          />
        </div>

        <div className="space-y-4">
          {(evaluating || evaluation) && (
            <EvaluationCard evaluation={evaluation} loading={evaluating} />
          )}
          <div className="rounded-xl bg-[#F0EFEA] p-5">
            <p className="text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
              Duplicate check
            </p>
            {!analysis ? (
              <p className="mt-2 text-sm text-[#8C8A82]">
                Add a photo to compare the item with your wardrobe.
              </p>
            ) : !health?.llm ? (
              <p className="mt-2 text-sm text-[#1C1C1C]">
                The duplicate explanation needs an LLM key on the server. The detected item and
                matches below are still real.
              </p>
            ) : duplicate?.duplicate ? (
              <div className="mt-2 space-y-2">
                <span className="inline-block rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-800">
                  Possible duplicate
                </span>
                <p className="text-sm text-[#1C1C1C]">
                  {duplicate.note || "The stylist found a similar item in your wardrobe."}
                </p>
                {duplicateItem && (
                  <p className="text-xs text-[#8C8A82]">
                    Closest match: <b className="text-[#1C1C1C]">{duplicateItem.name}</b>
                  </p>
                )}
              </div>
            ) : (
              <div className="mt-2 space-y-2">
                <span className="inline-block rounded-full bg-[#E8EDE0] px-2.5 py-1 text-xs font-semibold text-[#556B2F]">
                  No clear duplicate
                </span>
                <p className="text-sm text-[#1C1C1C]">
                  {duplicate?.note || "The stylist did not find a confident duplicate."}
                </p>
              </div>
            )}
          </div>

          <div className="rounded-xl bg-[#F0EFEA] p-5">
            <p className="text-xs font-semibold uppercase tracking-widest text-[#8C8A82]">
              Similar items you own
            </p>
            {!analysis ? (
              <p className="mt-2 text-sm text-[#8C8A82]">Results appear after an analysis.</p>
            ) : similar.length ? (
              <div className="mt-2 space-y-2">
                {similar.map((item) => (
                  <div
                    key={item.id}
                    className="flex items-center gap-3 rounded-lg border border-[#E2E0D8] bg-white p-2"
                  >
                    <div className="h-12 w-10 shrink-0 overflow-hidden rounded bg-[#F0EFEA]">
                      {item.cutout_url ? (
                        <img
                          src={asset(item.cutout_url)}
                          alt={item.name}
                          className="h-full w-full object-contain"
                        />
                      ) : null}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-semibold text-[#1C1C1C]">{item.name}</p>
                      <p className="truncate text-[10px] text-[#8C8A82]">
                        {cap(item.color_name ?? "unknown")} - {cap(item.category)}
                      </p>
                    </div>
                    {item.color_name === analysis.color_name && (
                      <span className="rounded-full bg-[#E8EDE0] px-2 py-0.5 text-[10px] font-semibold text-[#556B2F]">
                        Same colour
                      </span>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-2 text-sm text-[#8C8A82]">
                Nothing similar in your wardrobe yet.
              </p>
            )}
          </div>

          <div className="rounded-xl border border-[#E2E0D8] bg-white p-4 text-xs text-[#8C8A82]">
            This analysis uses the item photo. Price comparison and retail catalogue matching are
            not connected on this branch yet.
          </div>
        </div>
      </div>
    </div>
  )
}
