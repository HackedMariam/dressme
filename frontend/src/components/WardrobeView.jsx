import { useEffect, useMemo, useRef, useState } from 'react'
import { api, cap, seasonLabel, TAXONOMY, COLORS } from '../api'
import LiveScan from './LiveScan'

// --- smart text search -------------------------------------------------
// Recognises taxonomy words in free text ("a dress for a party" -> category
// "dress" + occasion "party") instead of requiring every raw word to appear
// verbatim, and relaxes the least important filters first when they're too
// strict to return anything, instead of showing an empty grid.
const STOPWORDS = new Set(['a', 'an', 'the', 'for', 'to', 'of', 'in', 'on', 'with', 'my', 'me', 'i', 'is',
  'are', 'some', 'any', 'please', 'show', 'find', 'want', 'need', 'looking', 'look', 'that', 'this'])
const DROP_ORDER = ['pattern', 'style', 'season', 'occasion', 'color']

function buildSearchTerms() {
  const terms = []
  const add = (field, values, test) =>
    values.forEach((v) => terms.push({ field, phrase: v.toLowerCase(), test: (item) => test(item, v) }))
  add('category', TAXONOMY.classes, (i, v) => i.category === v)
  add('category', TAXONOMY.groups, (i, v) => i.category_group === v)
  add('color', Object.keys(COLORS), (i, v) => i.color_name === v)
  add('color', TAXONOMY.colorFamilies, (i, v) => i.color_family === v)
  add('season', TAXONOMY.seasons, (i, v) => (i.seasons || []).includes(v))
  add('occasion', TAXONOMY.occasions, (i, v) => (i.occasions || []).includes(v))
  add('style', TAXONOMY.styles, (i, v) => i.style === v)
  add('pattern', TAXONOMY.patterns, (i, v) => i.pattern === v)
  return terms.sort((a, b) => b.phrase.length - a.phrase.length) // longest phrase first ("hot pink" before "pink")
}
const SEARCH_TERMS = buildSearchTerms()
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

function parseQuery(q) {
  const text = q.toLowerCase().trim()
  if (!text) return null
  let remaining = ` ${text} `
  const terms = []
  for (const t of SEARCH_TERMS) {
    for (const variant of [t.phrase, t.phrase + 's', t.phrase + 'es']) {
      const re = new RegExp(`\\b${esc(variant)}\\b`)
      if (re.test(remaining)) {
        terms.push(t)
        remaining = remaining.replace(re, ' ')
        break
      }
    }
  }
  const freeWords = remaining.split(/\s+/).filter((w) => w && !STOPWORDS.has(w))
  return { terms, freeWords }
}

function smartMatch(items, parsed) {
  const haystack = (i) => [i.name, i.color_name, i.category, i.subcategory, i.style, i.pattern,
    i.material, ...(i.seasons || []), ...(i.occasions || []), ...(i.tags || [])].join(' ').toLowerCase()
  const test = (dropSet) => items.filter((i) => {
    if (!parsed.terms.every((t) => dropSet.has(t.field) || t.test(i))) return false
    if (parsed.freeWords.length && !parsed.freeWords.every((w) => haystack(i).includes(w))) return false
    return true
  })
  let dropSet = new Set()
  let result = test(dropSet)
  for (const field of DROP_ORDER) {
    if (result.length) break
    dropSet = new Set([...dropSet, field])
    result = test(dropSet)
  }
  return result
}

const STEPS = ['Detecting the item', 'Removing background & reading colour', 'Classifying occasion, style & colour', 'Saving to your wardrobe']

function Pending({ job }) {
  const [step, setStep] = useState(0)
  useEffect(() => {
    if (job.error) return
    const t = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 1400)
    return () => clearInterval(t)
  }, [job.error])
  return (
    <div className={`card pending ${job.error ? 'failed' : ''}`}>
      <div className="thumb">
        <img src={job.preview} alt="" style={{ opacity: 0.35 }} />
        {!job.error && <div className="scan" />}
      </div>
      <div className="card-body">
        <div className="group">{job.error ? 'Could not add' : 'Analysing…'}</div>
        <div className="steps">
          {job.error ? <p className="err">{job.error}</p> : STEPS.map((s, i) => (
            <div key={s} className={`step ${i < step ? 'done' : i === step ? 'now' : ''}`}>{s}</div>
          ))}
        </div>
      </div>
    </div>
  )
}

export function ItemCard({ item, selected, onClick }) {
  const conf = item.confidence ?? 0
  const low = conf < 0.6
  const date = item.created_at ? new Date(item.created_at).toLocaleDateString('en', { month: 'short', day: 'numeric' }) : ''
  return (
    <button className={`card ${selected ? 'selected' : ''}`} onClick={onClick}>
      <div className="thumb">
        {item.cutout_url && <img src={item.cutout_url} alt={item.name} loading="lazy" />}
        {item.needs_review && <span className="badge review"><i />Needs review</span>}
        {item.style && <span className="badge style">{cap(item.style)}</span>}
      </div>
      <div className="card-body">
        <div className="group">{item.category_group}</div>
        <div className="name">{item.name}</div>
        <div className="meta">
          <span className="dot" style={{ background: item.color_hex }} />
          <span>{cap(item.color_name)} · {seasonLabel(item.seasons)} · {(item.occasions || []).slice(0, 2).map(cap).join(', ') || cap(item.pattern || 'solid')}</span>
        </div>
        <div className="foot">
          <span>Added {date}</span>
          <span className="bar"><span style={{ width: `${conf * 100}%` }} className={low ? 'low' : ''} /></span>
          <b className={low ? 'low' : ''}>{Math.round(conf * 100)}% sure</b>
        </div>
      </div>
    </button>
  )
}

const SpeechRecognition = typeof window !== 'undefined'
  && (window.SpeechRecognition || window.webkitSpeechRecognition)

export default function WardrobeView({ items, health, selectedId, onSelect, onAdded }) {
  const [q, setQ] = useState('')
  const [color, setColor] = useState('')
  const [season, setSeason] = useState('')
  const [occasion, setOccasion] = useState('')
  const [style, setStyle] = useState('')
  const [group, setGroup] = useState('All')
  const [reviewOnly, setReviewOnly] = useState(false)
  const [jobs, setJobs] = useState([])
  const [drag, setDrag] = useState(false)
  const [multi, setMulti] = useState(false)
  const [listening, setListening] = useState(false)
  const [photoSearch, setPhotoSearch] = useState(null) // { category, color_name, match, error }
  const [photoSearching, setPhotoSearching] = useState(false)
  const [agentSearch, setAgentSearch] = useState(null) // { reply, itemIds, error }
  const [agentSearching, setAgentSearching] = useState(false)
  const [scanning, setScanning] = useState(false)
  const fileRef = useRef()
  const photoRef = useRef()
  const recRef = useRef()

  function toggleMic() {
    if (!SpeechRecognition) return
    if (listening) { recRef.current?.stop(); return }
    const rec = new SpeechRecognition()
    rec.lang = 'en-US'
    rec.interimResults = false
    rec.maxAlternatives = 1
    rec.onresult = (e) => setQ(e.results[0][0].transcript)
    rec.onend = () => setListening(false)
    rec.onerror = () => setListening(false)
    recRef.current = rec
    rec.start()
    setListening(true)
  }

  async function handlePhotoSearch(file) {
    if (!file) return
    setPhotoSearching(true)
    setPhotoSearch(null)
    setAgentSearch(null)
    try {
      const { category, color_name, match } = await api.searchByPhoto(file)
      setPhotoSearch({ category, color_name, match })
      if (match) onSelect(match.id)
    } catch (e) {
      setPhotoSearch({ error: e.message })
    } finally {
      setPhotoSearching(false)
    }
  }

  async function handleAgentSearch() {
    const message = q.trim()
    if (!message) return
    setAgentSearching(true)
    setAgentSearch(null)
    setPhotoSearch(null)
    try {
      const { reply, items: found } = await api.agentSearch(message)
      setAgentSearch({ reply, itemIds: new Set(found.map((i) => i.id)) })
    } catch (e) {
      setAgentSearch({ error: e.message })
    } finally {
      setAgentSearching(false)
    }
  }

  const counts = useMemo(() => {
    const c = { All: items.length }
    TAXONOMY.groups.forEach((g) => (c[g] = items.filter((i) => i.category_group === g).length))
    return c
  }, [items])
  const toReview = items.filter((i) => i.needs_review).length
  const colors = [...new Set(items.map((i) => i.color_name).filter(Boolean))].sort()

  const parsedQuery = useMemo(() => parseQuery(q), [q])

  let shown
  if (photoSearch) {
    shown = photoSearch.match ? [photoSearch.match] : []
  } else if (agentSearch?.itemIds) {
    shown = items.filter((i) => agentSearch.itemIds.has(i.id))
  } else {
    shown = items.filter((i) =>
      (group === 'All' || i.category_group === group) &&
      (!reviewOnly || i.needs_review) &&
      (!color || i.color_name === color) &&
      (!season || (i.seasons || []).includes(season)) &&
      (!occasion || (i.occasions || []).includes(occasion)) &&
      (!style || i.style === style))
    if (parsedQuery) shown = smartMatch(shown, parsedQuery)
  }

  async function handleFiles(fileList) {
    const files = [...fileList].filter((f) => f.type.startsWith('image/'))
    if (!files.length) return
    for (const file of files) {
      const id = Math.random().toString(36).slice(2)
      setJobs((j) => [...j, { id, preview: URL.createObjectURL(file) }])
      try {
        const { items: added } = await api.analyze(file, multi)
        onAdded(added)
        setJobs((j) => j.filter((x) => x.id !== id))
      } catch (e) {
        setJobs((j) => j.map((x) => (x.id === id ? { ...x, error: e.message } : x)))
        setTimeout(() => setJobs((j) => j.filter((x) => x.id !== id)), 6000)
      }
    }
  }

  return (
    <div className="wardrobe">
      <header className="page-head">
        <div>
          <h1>My Wardrobe</h1>
          <p className="sub">
            {items.length} items · {items.filter((i) => i.status !== 'confirmed').length - toReview} detected automatically · {toReview} to review
          </p>
        </div>
        <div className="head-actions">
          <button className="btn ghost" disabled={health && !health.model_loaded} onClick={() => setScanning(true)}>📹 Live scan</button>
          <button className="btn primary" disabled={health && !health.model_loaded} onClick={() => fileRef.current.click()}>＋ Add clothing</button>
        </div>
        <input ref={fileRef} type="file" accept="image/*" multiple hidden
          onChange={(e) => { handleFiles(e.target.files); e.target.value = '' }} />
      </header>

      {scanning && <LiveScan onAdded={onAdded} onClose={() => setScanning(false)} />}

      <div className={`dropzone ${drag ? 'drag' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); handleFiles(e.dataTransfer.files) }}
        onClick={() => fileRef.current.click()}>
        <p>Drop photos here. We detect each item, remove the background, and classify it by occasion, style, colour and season.</p>
        <small>You can correct anything we get wrong.</small>
        <label className="multi" onClick={(e) => e.stopPropagation()}>
          <input type="checkbox" checked={multi} onChange={(e) => setMulti(e.target.checked)} />
          Photo of a full outfit — add every item found
        </label>
      </div>

      <div className="filters">
        <div className="search">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></svg>
          <input placeholder="Search instantly, or press Enter to ask the AI stylist…" value={q}
            onChange={(e) => { setQ(e.target.value); setPhotoSearch(null); setAgentSearch(null) }}
            onKeyDown={(e) => { if (e.key === 'Enter') handleAgentSearch() }} />
          <button type="button" className="icon-btn" title="Ask the AI stylist"
            disabled={agentSearching || !q.trim()} onClick={handleAgentSearch}>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M12 3v4M12 17v4M3 12h4M17 12h4M6.3 6.3l2.8 2.8M14.9 14.9l2.8 2.8M17.7 6.3l-2.8 2.8M9.1 14.9l-2.8 2.8" />
            </svg>
          </button>
          {SpeechRecognition && (
            <button type="button" className={`icon-btn ${listening ? 'on' : ''}`} title="Search by voice"
              onClick={toggleMic}>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
                <rect x="9" y="2" width="6" height="12" rx="3" /><path d="M5 11a7 7 0 0 0 14 0" />
                <path d="M12 18v3" />
              </svg>
            </button>
          )}
          <button type="button" className="icon-btn" title="Search by photo" disabled={photoSearching}
            onClick={() => photoRef.current.click()}>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M4 8h3l1.5-2h7L17 8h3v11H4z" /><circle cx="12" cy="13.5" r="3.5" />
            </svg>
          </button>
          <input ref={photoRef} type="file" accept="image/*" capture="environment" hidden
            onChange={(e) => { handlePhotoSearch(e.target.files[0]); e.target.value = '' }} />
        </div>
        <select value={color} onChange={(e) => setColor(e.target.value)}>
          <option value="">All colors</option>
          {colors.map((c) => <option key={c} value={c}>{cap(c)}</option>)}
        </select>
        <select value={season} onChange={(e) => setSeason(e.target.value)}>
          <option value="">All seasons</option>
          {TAXONOMY.seasons.map((s) => <option key={s} value={s}>{cap(s)}</option>)}
        </select>
        <select value={occasion} onChange={(e) => setOccasion(e.target.value)}>
          <option value="">All occasions</option>
          {TAXONOMY.occasions.map((s) => <option key={s} value={s}>{cap(s)}</option>)}
        </select>
        <select value={style} onChange={(e) => setStyle(e.target.value)}>
          <option value="">All styles</option>
          {TAXONOMY.styles.map((s) => <option key={s} value={s}>{cap(s)}</option>)}
        </select>
      </div>

      {photoSearching && <p className="banner">Looking for that item in your wardrobe…</p>}
      {photoSearch?.error && <p className="banner failed">{photoSearch.error}</p>}
      {photoSearch && !photoSearching && !photoSearch.error && (
        <p className={`banner ${photoSearch.match ? '' : 'failed'}`}>
          {photoSearch.match
            ? <>That looks like your <b>{photoSearch.match.name}</b>.</>
            : <>No {cap(photoSearch.color_name || '')} {photoSearch.category || 'item'} like that in your wardrobe yet.</>}
          {' '}<button className="link" onClick={() => setPhotoSearch(null)}>Clear</button>
        </p>
      )}

      {agentSearching && <p className="banner agent">Asking the stylist…</p>}
      {agentSearch?.error && <p className="banner failed">{agentSearch.error}</p>}
      {agentSearch && !agentSearching && !agentSearch.error && (
        <p className="banner agent">
          <b>Stylist:</b> {agentSearch.reply}
          {' '}<button className="link" onClick={() => setAgentSearch(null)}>Clear</button>
        </p>
      )}

      <div className="chips">
        {['All', ...TAXONOMY.groups].filter((g) => g === 'All' || counts[g] > 0).map((g) => (
          <button key={g} className={`chip ${group === g ? 'on' : ''}`} onClick={() => setGroup(g)}>
            {g} <span>{counts[g]}</span>
          </button>
        ))}
        {toReview > 0 && (
          <button className={`chip review ${reviewOnly ? 'on' : ''}`} onClick={() => setReviewOnly(!reviewOnly)}>
            Needs review ({toReview})
          </button>
        )}
      </div>

      <div className="grid">
        {jobs.map((j) => <Pending key={j.id} job={j} />)}
        {shown.map((i) => (
          <ItemCard key={i.id} item={i} selected={i.id === selectedId} onClick={() => onSelect(i.id)} />
        ))}
        {!shown.length && !jobs.length && (
          <p className="empty">{items.length ? 'No items match these filters.' : 'Your wardrobe is empty — add a photo of a clothing item to start.'}</p>
        )}
      </div>
    </div>
  )
}
