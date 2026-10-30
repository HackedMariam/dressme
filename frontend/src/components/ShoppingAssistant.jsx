import { useRef, useState } from 'react'
import { API } from '../api'
import { supabase } from '../supabase'

// ── helpers ──────────────────────────────────────────────────────────────────
const VERDICT_META = {
  BUY:     { label: 'Buy It',    cls: 'verdict-buy'     },
  CONSIDER:{ label: 'Consider',  cls: 'verdict-consider'},
  SKIP:    { label: "Don't Buy", cls: 'verdict-skip'    },
}

async function authHeaders() {
  const headers = {}
  if (supabase) {
    const { data } = await supabase.auth.getSession()
    if (data.session) headers.Authorization = `Bearer ${data.session.access_token}`
  }
  return headers
}

async function callEvaluate({ imageFile, imageUrl, prompt, price, budget }) {
  const fd = new FormData()
  if (imageFile) fd.append('image_file', imageFile)
  if (imageUrl)  fd.append('image_url',  imageUrl)
  fd.append('prompt', prompt || 'Should I buy this?')
  fd.append('price',  String(price  || 0))
  fd.append('budget', String(budget || 0))

  const headers = await authHeaders()
  const res = await fetch(`${API}/api/shopping-assistant/evaluate`, {
    method: 'POST', body: fd, headers,
  })
  const json = await res.json()
  if (!res.ok) throw new Error(json.detail || `HTTP ${res.status}`)
  return json
}

// ── component ─────────────────────────────────────────────────────────────────
export default function ShoppingAssistant() {
  const fileRef  = useRef(null)

  const [imageFile,   setImageFile]   = useState(null)
  const [imagePreview,setImagePreview]= useState(null)
  const [imageUrl,    setImageUrl]    = useState('')
  const [prompt,      setPrompt]      = useState('')
  const [price,       setPrice]       = useState('')
  const [budget,      setBudget]      = useState('')
  const [loading,     setLoading]     = useState(false)
  const [result,      setResult]      = useState(null)
  const [error,       setError]       = useState(null)
  const [drag,        setDrag]        = useState(false)

  // ── file helpers ────────────────────────────────────────────────────────────
  function pickFile(file) {
    if (!file || !file.type.startsWith('image/')) return
    setImageFile(file)
    setImageUrl('')
    setResult(null)
    setError(null)
    const reader = new FileReader()
    reader.onload = (e) => setImagePreview(e.target.result)
    reader.readAsDataURL(file)
  }

  function clearImage() {
    setImageFile(null); setImagePreview(null); setImageUrl(''); setResult(null); setError(null)
  }

  // ── drag & drop ─────────────────────────────────────────────────────────────
  function onDrop(e) {
    e.preventDefault(); setDrag(false)
    const file = e.dataTransfer.files?.[0]
    if (file) pickFile(file)
  }

  // ── submit ──────────────────────────────────────────────────────────────────
  async function handleSubmit(e) {
    e.preventDefault()
    if (!imageFile && !imageUrl.trim()) { setError('Please attach an image or paste a URL.'); return }
    setLoading(true); setError(null); setResult(null)
    try {
      const data = await callEvaluate({
        imageFile,
        imageUrl: imageUrl.trim(),
        prompt,
        price:  parseFloat(price)  || 0,
        budget: parseFloat(budget) || 0,
      })
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // ── result values ────────────────────────────────────────────────────────────
  const verdict      = result?.agent_verdict?.decision?.toUpperCase()
  const verdictMeta  = VERDICT_META[verdict] || {}
  const score        = result?.agent_verdict?.score
  const reasons      = result?.agent_verdict?.reasons || []
  const candidate    = result?.candidate_item || {}
  const evidence     = result?.tool_evidence || {}
  const stylist      = result?.stylist_interpretation
  const outfits      = evidence?.matching_outfits || []

  // ── render ──────────────────────────────────────────────────────────────────
  return (
    <div className="sa-wrap">
      {/* ── header ── */}
      <div className="page-head">
        <div>
          <h1>Shopping<br /><span style={{ color: 'var(--lime)' }}>Assistant</span></h1>
          <p className="sub">Upload or link an item — we'll tell you if it's worth buying.</p>
        </div>
      </div>

      <div className="sa-layout">
        {/* ── LEFT: form ── */}
        <form className="sa-form" onSubmit={handleSubmit}>

          {/* image input */}
          <div className="sa-section-label">Item Image</div>

          {/* dropzone / preview */}
          {!imagePreview ? (
            <div
              className={`dropzone sa-drop ${drag ? 'drag' : ''}`}
              onClick={() => fileRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
              onDragLeave={() => setDrag(false)}
              onDrop={onDrop}
            >
              <p>📎 Drop a photo here or <u>browse</u></p>
              <small>JPG · PNG · WEBP — max 10 MB</small>
              <input
                ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }}
                onChange={(e) => pickFile(e.target.files?.[0])}
              />
            </div>
          ) : (
            <div className="sa-preview-wrap">
              <img src={imagePreview} alt="preview" className="sa-preview-img" />
              <button type="button" className="sa-clear-btn" onClick={clearImage} title="Remove image">✕</button>
            </div>
          )}

          {/* — OR paste URL — */}
          {!imageFile && (
            <>
              <div className="sa-or-divider"><span>or</span></div>
              <input
                className="sa-url-input"
                type="url"
                placeholder="Paste image URL (https://…)"
                value={imageUrl}
                onChange={(e) => { setImageUrl(e.target.value); setResult(null); setError(null) }}
              />
            </>
          )}

          {/* prompt */}
          <div className="sa-section-label" style={{ marginTop: 20 }}>Your Question</div>
          <textarea
            className="sa-textarea"
            rows={3}
            placeholder="e.g. Should I buy this for work? I already own a navy blazer…"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />

          {/* price + budget */}
          <div className="sa-section-label" style={{ marginTop: 20 }}>Budget</div>
          <div className="sa-price-row">
            <label className="sa-price-group">
              <span>Item Price (\$)</span>
              <input
                type="number" min="0" step="0.01" placeholder="e.g. 79.99"
                value={price} onChange={(e) => setPrice(e.target.value)}
              />
            </label>
            <label className="sa-price-group">
              <span>My Budget (\$)</span>
              <input
                type="number" min="0" step="0.01" placeholder="e.g. 100"
                value={budget} onChange={(e) => setBudget(e.target.value)}
              />
            </label>
          </div>

          {error && <div className="banner failed" style={{ marginTop: 14 }}>{error}</div>}

          <button
            type="submit"
            className="btn primary sa-submit"
            disabled={loading || (!imageFile && !imageUrl.trim())}
          >
            {loading ? 'Analysing…' : '✦ Analyse This Item'}
          </button>
        </form>

        {/* ── RIGHT: result ── */}
        <div className="sa-result-col">
          {!result && !loading && (
            <div className="sa-empty">
              <div className="sa-empty-icon">🛍️</div>
              <p>Fill in the form on the left and hit <strong>Analyse</strong> to get your personalised verdict.</p>
            </div>
          )}

          {loading && (
            <div className="sa-empty">
              <div className="sa-spinner" />
              <p className="muted" style={{ marginTop: 14 }}>Running AI evaluation…</p>
            </div>
          )}

          {result && (
            <div className="sa-result">
              {/* verdict pill */}
              <div className={`sa-verdict ${verdictMeta.cls || ''}`}>
                <span className="sa-verdict-label">{verdictMeta.label || verdict}</span>
                {score != null && (
                  <span className="sa-verdict-score">{Math.round(score)}/100</span>
                )}
              </div>

              {/* detected info */}
              {(candidate.detected_category || candidate.detected_color) && (
                <div className="sa-tags">
                  {candidate.detected_category && <span className="chip">{candidate.detected_category}</span>}
                  {candidate.detected_color     && <span className="chip">{candidate.detected_color}</span>}
                  {candidate.inferred_occasion  && <span className="chip">{candidate.inferred_occasion.replace('_', ' ')}</span>}
                </div>
              )}

              {/* stylist text */}
              {stylist && (
                <div className="sa-stylist">
                  <div className="sa-box-label">Stylist's Recommendation</div>
                  <div className="sa-stylist-body">{stylist}</div>
                </div>
              )}

              {/* key metrics */}
              <div className="sa-metrics">
                <div className="sa-metric">
                  <span className="sa-metric-label">Redundancy Risk</span>
                  <div className="sa-meter">
                    <div className="sa-meter-fill" style={{ width: `${evidence.redundancy_score || 0}%`,
                      background: (evidence.redundancy_score || 0) > 60 ? 'var(--amber)' : 'var(--olive)' }} />
                  </div>
                  <span className="sa-metric-val">{evidence.redundancy_score ?? '—'}%</span>
                </div>
                <div className="sa-metric">
                  <span className="sa-metric-label">Wardrobe Gap Fill</span>
                  <div className="sa-meter">
                    <div className="sa-meter-fill" style={{ width: `${evidence.wardrobe_gap_score || 0}%`,
                      background: 'var(--olive)' }} />
                  </div>
                  <span className="sa-metric-val">{evidence.wardrobe_gap_score?.toFixed(0) ?? '—'}/100</span>
                </div>
                <div className="sa-metric">
                  <span className="sa-metric-label">Outfit Compatibility</span>
                  <div className="sa-meter">
                    <div className="sa-meter-fill" style={{ width: `${evidence.compatible_outfits_count * 15 > 100 ? 100 : evidence.compatible_outfits_count * 15 || 0}%`,
                      background: 'var(--olive)' }} />
                  </div>
                  <span className="sa-metric-val">{evidence.compatible_outfits_count ?? 0} outfits</span>
                </div>
              </div>

              {/* closest match */}
              {evidence.closest_wardrobe_match && (
                <div className="sa-info-row">
                  <span className="sa-info-key">Closest wardrobe match</span>
                  <span className="sa-info-val">{evidence.closest_wardrobe_match}</span>
                </div>
              )}

              {/* budget */}
              {(candidate.price > 0 || candidate.budget > 0) && (
                <div className="sa-info-row">
                  <span className="sa-info-key">Price vs Budget</span>
                  <span className="sa-info-val">
                    \${candidate.price} vs \${candidate.budget}
                    {evidence.budget_penalty > 0 && (
                      <span style={{ color: 'var(--amber)', marginLeft: 6 }}>
                        (−{evidence.budget_penalty.toFixed(0)} pts penalty)
                      </span>
                    )}
                  </span>
                </div>
              )}

              {/* XGBoost */}
              {evidence.xgboost_prediction && (
                <div className="sa-info-row">
                  <span className="sa-info-key">ML Prediction</span>
                  <span className="sa-info-val">
                    {evidence.xgboost_prediction}
                    {evidence.xgboost_confidence != null && (
                      <span className="muted" style={{ marginLeft: 6 }}>
                        ({(evidence.xgboost_confidence * 100).toFixed(0)}% confidence)
                      </span>
                    )}
                  </span>
                </div>
              )}

              {/* reasons */}
              {reasons.length > 0 && (
                <div className="sa-reasons">
                  <div className="sa-box-label">Reasoning</div>
                  <ul>
                    {reasons.map((r, i) => <li key={i}>{r}</li>)}
                  </ul>
                </div>
              )}

              {/* outfits */}
              {outfits.length > 0 && (
                <div className="sa-outfits">
                  <div className="sa-box-label">Ready-to-Wear Pairings</div>
                  {outfits.map((o, i) => (
                    <div key={i} className="sa-outfit-card">
                      <div className="sa-outfit-score">
                        <div className="foot bar" style={{ maxWidth: 60 }}>
                          <span style={{ width: `${o.compatibility_score}%` }} />
                        </div>
                        <b>{Math.round(o.compatibility_score)}%</b>
                      </div>
                      <p>{o.description}</p>
                      {o.paired_items?.length > 0 && (
                        <div className="sa-outfit-items">
                          {o.paired_items.map((p, j) => (
                            <span key={j} className="chip" style={{ fontSize: 13 }}>
                              {p.name || p.category}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
