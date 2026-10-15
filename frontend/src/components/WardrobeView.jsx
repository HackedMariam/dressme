import { useEffect, useMemo, useRef, useState } from 'react'
import { api, cap, seasonLabel, TAXONOMY } from '../api'

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
  const fileRef = useRef()

  const counts = useMemo(() => {
    const c = { All: items.length }
    TAXONOMY.groups.forEach((g) => (c[g] = items.filter((i) => i.category_group === g).length))
    return c
  }, [items])
  const toReview = items.filter((i) => i.needs_review).length
  const colors = [...new Set(items.map((i) => i.color_name).filter(Boolean))].sort()

  const shown = items.filter((i) => {
    if (group !== 'All' && i.category_group !== group) return false
    if (reviewOnly && !i.needs_review) return false
    if (color && i.color_name !== color) return false
    if (season && !(i.seasons || []).includes(season)) return false
    if (occasion && !(i.occasions || []).includes(occasion)) return false
    if (style && i.style !== style) return false
    if (q) {
      const hay = [i.name, i.color_name, i.category, i.subcategory, i.style, i.pattern, i.material,
        ...(i.seasons || []), ...(i.occasions || []), ...(i.tags || [])].join(' ').toLowerCase()
      if (!q.toLowerCase().split(/\s+/).every((w) => hay.includes(w))) return false
    }
    return true
  })

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
        <button className="btn primary" disabled={health && !health.model_loaded} onClick={() => fileRef.current.click()}>＋ Add clothing</button>
        <input ref={fileRef} type="file" accept="image/*" multiple hidden
          onChange={(e) => { handleFiles(e.target.files); e.target.value = '' }} />
      </header>

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
          <input placeholder="Search by name, color, season, occasion…" value={q} onChange={(e) => setQ(e.target.value)} />
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
