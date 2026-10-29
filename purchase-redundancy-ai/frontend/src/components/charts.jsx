import React, { useState } from 'react';
import Icon from './Icon';

// Shared chart pieces (dashboard, advisor). Verdicts are statuses: fixed status colors, always with a label.
export const VERDICT_SERIES = [
  { key: 'buy', label: 'Acheter', color: 'var(--status-good)' },
  { key: 'consider', label: 'À réfléchir', color: 'var(--status-warning)' },
  { key: 'skip', label: 'Inutile (doublon)', color: 'var(--status-critical)' },
];

export function Kpi({ label, value, hint }) {
  return (
    <div className="kpi">
      <span>{label}</span>
      <strong>{value}</strong>
      {hint && <small>{hint}</small>}
    </div>
  );
}

export function Legend({ series }) {
  return (
    <ul className="legend" aria-label="Légende">
      {series.map((s) => <li key={s.key}><span className="swatch" style={{ background: s.color }} />{s.label}</li>)}
    </ul>
  );
}

/** One bar per day, verdict segments stacked from the baseline, 2px surface gap, hover tooltip */
export function StackedColumns({ rows, series }) {
  const [hover, setHover] = useState(null);
  const width = 720;
  const height = 220;
  const pad = { top: 12, right: 8, bottom: 26, left: 32 };
  const max = Math.max(1, ...rows.map((r) => r.total));
  const ticks = niceTicks(max);
  const top = ticks[ticks.length - 1];
  const slot = (width - pad.left - pad.right) / rows.length;
  const bar = Math.max(2, Math.min(24, slot - 2));
  const y = (v) => pad.top + (height - pad.top - pad.bottom) * (1 - v / top);
  const labelEvery = Math.ceil(rows.length / 6);

  return (
    <div className="chart-wrap" onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Verdicts par jour (barres empilées)" className="chart-svg">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)} className="grid-line" />
            <text x={pad.left - 6} y={y(t) + 4} textAnchor="end" className="axis-text">{t}</text>
          </g>
        ))}
        {rows.map((r, i) => {
          const x = pad.left + i * slot + (slot - bar) / 2;
          let base = 0;
          const segments = series.filter((s) => r[s.key] > 0);
          return (
            <g key={r.date}>
              {segments.map((s, j) => {
                const y0 = y(base);
                const y1 = y(base + r[s.key]);
                base += r[s.key];
                const isTop = j === segments.length - 1;
                const gap = j > 0 ? 2 : 0; // surface gap between stacked segments
                const h = Math.max(1, y0 - y1 - gap);
                return isTop
                  ? <path key={s.key} d={roundedTop(x, y1, bar, h, Math.min(4, bar / 2, h))} fill={s.color} />
                  : <rect key={s.key} x={x} y={y1 + 0} width={bar} height={h} fill={s.color} />;
              })}
              {/* hit target: the whole column slot, taller than the mark */}
              <rect x={pad.left + i * slot} y={pad.top} width={slot} height={height - pad.top - pad.bottom} fill="transparent"
                onMouseEnter={() => setHover({ i, row: r })} onFocus={() => setHover({ i, row: r })} tabIndex={r.total ? 0 : -1}
                aria-label={`${formatDay(r.date)} : ${r.total} analyse(s)`} />
              {(i % labelEvery === 0 || i === rows.length - 1) && (
                <text x={pad.left + i * slot + slot / 2} y={height - 8} textAnchor="middle" className="axis-text">{formatDay(r.date)}</text>
              )}
            </g>
          );
        })}
        <line x1={pad.left} x2={width - pad.right} y1={y(0)} y2={y(0)} className="axis-line" />
      </svg>
      {hover && hover.row.total > 0 && (
        <div className="chart-tooltip" style={tooltipPosition((pad.left + (hover.i + 0.5) * slot) / width)}>
          <strong>{formatDay(hover.row.date, true)}</strong>
          {series.map((s) => hover.row[s.key] > 0 && (
            <div key={s.key}><span className="swatch" style={{ background: s.color }} />{s.label}<b>{hover.row[s.key]}</b></div>
          ))}
        </div>
      )}
    </div>
  );
}

export function VerdictTable({ rows }) {
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead><tr><th>Jour</th>{VERDICT_SERIES.map((s) => <th key={s.key}>{s.label}</th>)}<th>Total</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.date}><td>{formatDay(r.date, true)}</td>{VERDICT_SERIES.map((s) => <td key={s.key}>{r[s.key]}</td>)}<td>{r.total}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Horizontal bars - single series (the title names it), value at the bar end */
export function HBars({ data, unit }) {
  if (!data.length) return <p className="muted small empty-chart">Pas encore de données.</p>;
  const max = Math.max(...data.map(([, v]) => v));
  return (
    <ul className="hbars">
      {data.slice(0, 8).map(([label, value]) => (
        <li key={label} title={`${label} : ${value} ${unit}${value > 1 ? 's' : ''}`}>
          <span className="hbar-label">{label}</span>
          <span className="hbar-track"><span className="hbar-fill" style={{ width: `${(value / max) * 100}%` }} /></span>
          <span className="hbar-value">{value}</span>
        </li>
      ))}
    </ul>
  );
}

export function SystemHealth({ system }) {
  const analyze = system.routes.find((r) => r.route === 'POST /analyze');
  const hitRate = system.cache.hit_rate;
  return (
    <section className="card chart-card">
      <h3>Santé technique</h3>
      <p className="muted small">Depuis le démarrage du serveur ({formatUptime(system.uptime_s)}) · actualisé toutes les 15 s</p>
      <div className="kpi-row compact">
        <Kpi label="Requêtes / minute" value={system.requests_last_minute} hint={`${system.requests} au total`} />
        <Kpi label="Analyse (p95)" value={analyze?.p95_ms != null ? `${Math.round(analyze.p95_ms)} ms` : '—'} hint={analyze ? `${analyze.count} analyses` : null} />
        <Kpi label="Erreurs serveur" value={`${(system.error_rate_5xx * 100).toFixed(1)} %`} />
        <Kpi label={`Cache (${system.cache.backend === 'redis' ? 'Redis' : 'mémoire'})`} value={hitRate != null ? `${Math.round(hitRate * 100)} %` : '—'} hint="taux de succès" />
        <Kpi label="Base de données" value={system.database.dialect === 'postgresql' ? 'PostgreSQL' : 'SQLite'}
          hint={system.database.healthy ? 'opérationnelle' : 'injoignable'} />
        <Kpi label="Limites de débit" value={system.rate_limit.rejected} hint="requêtes refusées (429)" />
      </div>
      <details className="routes">
        <summary><Icon name="chart" size={16} /> Latence par route</summary>
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr><th>Route</th><th>Appels</th><th>p50</th><th>p95</th><th>4xx</th><th>5xx</th></tr></thead>
            <tbody>
              {system.routes.slice(0, 12).map((r) => (
                <tr key={r.route}>
                  <td><code>{r.route}</code></td><td>{r.count}</td>
                  <td>{r.p50_ms != null ? `${Math.round(r.p50_ms)} ms` : '—'}</td>
                  <td>{r.p95_ms != null ? `${Math.round(r.p95_ms)} ms` : '—'}</td>
                  <td>{r.errors_4xx}</td><td>{r.errors_5xx}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}

// ---------- helpers ----------

/** Keep the tooltip inside the card: centered on the column, anchored to the edge near the sides */
function tooltipPosition(fraction) {
  const left = `${fraction * 100}%`;
  if (fraction > 0.8) return { left, transform: 'translateX(calc(-100% + 12px))' };
  if (fraction < 0.2) return { left, transform: 'translateX(-12px)' };
  return { left };
}

export function fillDays(timeline, days) {
  const byDate = Object.fromEntries(timeline.map((d) => [d.date, d]));
  const rows = [];
  const today = new Date();
  for (let i = days - 1; i >= 0; i -= 1) {
    const d = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() - i));
    const key = d.toISOString().slice(0, 10);
    const row = byDate[key] || { buy: 0, consider: 0, skip: 0 };
    rows.push({ date: key, buy: row.buy, consider: row.consider, skip: row.skip, total: row.buy + row.consider + row.skip });
  }
  return rows;
}

function niceTicks(max) {
  const step = max <= 5 ? 1 : max <= 10 ? 2 : max <= 25 ? 5 : Math.ceil(max / 5 / 10) * 10;
  const ticks = [];
  for (let t = 0; t <= max + step - 1 && ticks.length < 7; t += step) ticks.push(t);
  if (ticks[ticks.length - 1] < max) ticks.push(ticks[ticks.length - 1] + step);
  return ticks;
}

function roundedTop(x, y, w, h, r) {
  return `M${x},${y + h} V${y + r} Q${x},${y} ${x + r},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${y + h} Z`;
}

export function formatDay(iso, long = false) {
  const d = new Date(`${iso}T00:00:00Z`);
  return d.toLocaleDateString('fr-FR', long ? { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' }
    : { day: 'numeric', month: 'short', timeZone: 'UTC' });
}

export function formatUptime(seconds) {
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h`;
  return `${Math.round(seconds / 86400)} j`;
}
