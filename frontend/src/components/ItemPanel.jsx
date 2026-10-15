import { useState } from 'react'
import { cap, COLORS, TAXONOMY } from '../api'

const pct = (v) => (v == null ? null : `${Math.round(v * 100)}% sure`)

function Label({ children, conf, note }) {
  const low = conf != null && conf < 0.6
  return (
    <div className="flabel">
      <span>{children}</span>
      {conf != null && <em className={low ? 'low' : ''}>{pct(conf)}</em>}
      {note && <em className="muted">{note}</em>}
    </div>
  )
}

function Multi({ options, value, onChange }) {
  const toggle = (o) => onChange(value.includes(o) ? value.filter((v) => v !== o) : [...value, o])
  return (
    <div className="multi-chips">
      {options.map((o) => (
        <button key={o} type="button" className={value.includes(o) ? 'on' : ''} onClick={() => toggle(o)}>{cap(o)}</button>
      ))}
    </div>
  )
}

export default function ItemPanel({ item, health, onClose, onSave, onReclassify, onDelete }) {
  const [f, setF] = useState({
    name: item.name, category: item.category, color_name: item.color_name, color_hex: item.color_hex,
    color_family: item.color_family || 'neutral',
    pattern: item.pattern || 'solid', seasons: item.seasons || [], style: item.style || 'casual',
    occasions: item.occasions || [], material: item.material || '', description: item.description || '',
  })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const fc = item.field_confidence || {}
  const set = (k) => (v) => setF((p) => ({ ...p, [k]: v?.target ? v.target.value : v }))

  const changed = Object.keys(f).filter((k) => JSON.stringify(f[k]) !== JSON.stringify(item[k] ?? (Array.isArray(f[k]) ? [] : '')))
  const dirty = changed.length > 0

  const run = async (fn) => {
    setBusy(true); setErr('')
    try { await fn() } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const save = (fields) => run(() => onSave(item.id, fields, true))

  const colorOptions = COLORS[f.color_name] ? Object.keys(COLORS) : [f.color_name, ...Object.keys(COLORS)]

  return (
    <aside className="panel">
      <div className="panel-head">
        <span>Item details</span>
        <button className="x" onClick={onClose} aria-label="Close">✕</button>
      </div>
      <div className="panel-img">{item.cutout_url && <img src={item.cutout_url} alt="" />}</div>
      {item.image_url && <a className="orig" href={item.image_url} target="_blank" rel="noreferrer">View original photo ↗</a>}

      <div className="group">{TAXONOMY.class_to_group[f.category]}</div>
      <input className="title-input" value={f.name} onChange={set('name')} />

      {item.needs_review && (
        <div className="warn"><b>We are not sure about this one.</b> Check the category first, then confirm or correct.</div>
      )}
      {item.status === 'confirmed' && <div className="ok">✓ Confirmed by you</div>}

      <Label conf={fc.category}>Category</Label>
      <select value={f.category} onChange={set('category')}>
        {TAXONOMY.groups.map((g) => (
          <optgroup key={g} label={g}>
            {TAXONOMY.classes.filter((c) => TAXONOMY.class_to_group[c] === g).map((c) => <option key={c} value={c}>{cap(c)}</option>)}
          </optgroup>
        ))}
      </select>
      {item.subcategory && item.subcategory !== item.category && <div className="hint">AI: {item.subcategory}</div>}

      <Label conf={fc.color} note={fc.color == null ? 'from the pixels' : null}>Color</Label>
      <div className="color-row">
        <span className="dot big" style={{ background: f.color_hex }} />
        <select value={f.color_name} onChange={(e) => setF((p) => ({ ...p, color_name: e.target.value, color_hex: COLORS[e.target.value] || p.color_hex }))}>
          {colorOptions.map((c) => <option key={c} value={c}>{cap(c)}</option>)}
        </select>
      </div>
      <div className="two" style={{ marginTop: 10 }}>
        <select value={f.color_family} onChange={set('color_family')} aria-label="Colour family">
          {TAXONOMY.colorFamilies.map((c) => <option key={c} value={c}>{cap(c)} tones</option>)}
        </select>
      </div>
      {item.colors?.length > 1 && (
        <div className="palette">
          {item.colors.slice(0, 4).map((c) => (
            <span key={c.hex} title={`${c.name} ${Math.round(c.share * 100)}%`} style={{ background: c.hex, flex: c.share }} />
          ))}
        </div>
      )}

      <div className="two">
        <div>
          <Label conf={fc.pattern}>Pattern</Label>
          <select value={f.pattern} onChange={set('pattern')}>
            {TAXONOMY.patterns.map((p) => <option key={p} value={p}>{cap(p)}</option>)}
          </select>
        </div>
        <div>
          <Label conf={fc.style}>Style</Label>
          <select value={f.style} onChange={set('style')}>
            {TAXONOMY.styles.map((p) => <option key={p} value={p}>{cap(p)}</option>)}
          </select>
        </div>
      </div>

      <Label conf={fc.season}>Season</Label>
      <Multi options={TAXONOMY.seasons} value={f.seasons} onChange={set('seasons')} />

      <Label conf={fc.occasion}>Occasions</Label>
      <Multi options={TAXONOMY.occasions} value={f.occasions} onChange={set('occasions')} />

      <Label conf={fc.material}>Material</Label>
      <input value={f.material} onChange={set('material')} />

      <Label>Description</Label>
      <textarea rows={3} value={f.description} onChange={set('description')} />

      {item.styling_tips?.length > 0 && (
        <div className="tips">
          <div className="flabel"><span>Styling tips</span></div>
          <ul>{item.styling_tips.map((t) => <li key={t}>{t}</li>)}</ul>
        </div>
      )}

      {err && <p className="err">{err}</p>}
      <div className="actions">
        <button className="btn primary" disabled={!dirty || busy}
          onClick={() => save(Object.fromEntries(changed.map((k) => [k, f[k]])))}>Save correction</button>
        <button className="btn ghost" disabled={busy} onClick={() => save({})}>Looks right</button>
      </div>
      <p className="note">Every correction is saved. It lets us measure how accurate detection really is, and improve it.</p>
      <div className="panel-foot">
        <span>{item.enrichment_source?.startsWith('llm') ? `Classified by ${item.enrichment_source.slice(4)}` : item.enrichment_source || ''}</span>
        {health?.llm && (
          <button className="link" disabled={busy} title="Ask the AI to classify this item again"
            onClick={() => run(() => onReclassify(item.id))}>{busy ? 'Working…' : 'Re-run AI'}</button>
        )}
        <button className="link danger" disabled={busy}
          onClick={() => confirm('Delete this item?') && run(() => onDelete(item.id))}>Delete</button>
      </div>
    </aside>
  )
}
