import { useEffect, useState } from 'react'
import { api, cap, TAXONOMY } from '../api'

function Bars({ values, total }) {
  const max = Math.max(1, ...values.map(([, n]) => n))
  return values.map(([k, n]) => (
    <div key={k} className="hbar"><span>{cap(k)}</span><div><i style={{ width: `${((total ? n / total : n / max)) * 100}%` }} /></div><b>{n}</b></div>
  ))
}

export default function Dashboard({ items, health }) {
  const [acc, setAcc] = useState([])
  useEffect(() => { api.accuracy().then(setAcc).catch(() => {}) }, [items])

  const byGroup = TAXONOMY.groups.map((g) => [g, items.filter((i) => i.category_group === g).length])
  const max = Math.max(1, ...byGroup.map(([, n]) => n))
  const colorCount = {}
  items.forEach((i) => { if (i.color_name) colorCount[i.color_name] = { n: (colorCount[i.color_name]?.n || 0) + 1, hex: i.color_hex } })
  const colors = Object.entries(colorCount).sort((a, b) => b[1].n - a[1].n)
  const byOccasion = TAXONOMY.occasions.map((o) => [o, items.filter((i) => (i.occasions || []).includes(o)).length])
    .filter(([, n]) => n).sort((a, b) => b[1] - a[1])
  const byStyle = TAXONOMY.styles.map((s) => [s, items.filter((i) => i.style === s).length])
    .filter(([, n]) => n).sort((a, b) => b[1] - a[1])
  const byFamily = TAXONOMY.colorFamilies.map((f) => [f, items.filter((i) => i.color_family === f).length]).filter(([, n]) => n)
  const avgConf = items.length ? items.reduce((s, i) => s + (i.confidence || 0), 0) / items.length : 0

  return (
    <div className="dashboard">
      <header className="page-head"><div><h1>Dashboard</h1><p className="sub">Your wardrobe at a glance</p></div></header>
      <div className="kpis">
        <div className="kpi"><b>{items.length}</b><span>items</span></div>
        <div className="kpi"><b>{items.filter((i) => i.needs_review).length}</b><span>to review</span></div>
        <div className="kpi"><b>{Math.round(avgConf * 100)}%</b><span>avg. detection confidence</span></div>
        <div className="kpi"><b>{health?.llm ? 'On' : 'Off'}</b><span>AI classification {health?.llm ? `(${health.llm_model})` : '(rules only)'}</span></div>
      </div>
      <div className="dash-grid">
        <section className="box">
          <h3>By category</h3>
          {byGroup.map(([g, n]) => (
            <div key={g} className="hbar"><span>{g}</span><div><i style={{ width: `${(n / max) * 100}%` }} /></div><b>{n}</b></div>
          ))}
        </section>
        <section className="box">
          <h3>Colour palette</h3>
          <div className="swatches">
            {colors.map(([c, { n, hex }]) => (
              <div key={c} className="sw"><span style={{ background: hex }} />{cap(c)} <b>{n}</b></div>
            ))}
          </div>
          <h3 style={{ marginTop: 24 }}>Season coverage</h3>
          {TAXONOMY.seasons.map((s) => {
            const n = items.filter((i) => (i.seasons || []).includes(s)).length
            return <div key={s} className="hbar"><span>{cap(s)}</span><div><i style={{ width: `${items.length ? (n / items.length) * 100 : 0}%` }} /></div><b>{n}</b></div>
          })}
        </section>
        <section className="box">
          <h3>By occasion</h3>
          {byOccasion.length ? <Bars values={byOccasion} total={items.length} /> : <p className="muted">No items yet.</p>}
          <h3 style={{ marginTop: 24 }}>By style</h3>
          {byStyle.length ? <Bars values={byStyle} total={items.length} /> : <p className="muted">No items yet.</p>}
          {byFamily.length > 0 && <>
            <h3 style={{ marginTop: 24 }}>Colour families</h3>
            <Bars values={byFamily} total={items.length} />
          </>}
        </section>
        <section className="box">
          <h3>Real detection accuracy</h3>
          <p className="muted">Measured on items you reviewed: a field counts as wrong when you corrected it.</p>
          {acc.length ? (
            <table>
              <thead><tr><th>Field</th><th>Reviewed</th><th>Corrected</th><th>Accuracy</th></tr></thead>
              <tbody>{acc.map((r) => (
                <tr key={r.field}><td>{cap(r.field.replace('_', ' '))}</td><td>{r.reviewed}</td><td>{r.corrected}</td>
                  <td>{r.accuracy == null ? '—' : `${Math.round(r.accuracy * 100)}%`}</td></tr>
              ))}</tbody>
            </table>
          ) : <p className="muted">Review a few items to see numbers here.</p>}
        </section>
      </div>
    </div>
  )
}
