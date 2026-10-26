import React, { useRef, useState } from 'react';
import { asset, resizeImage } from '../api';
import { categoryLabel, colorHex, colorLabel, formatPrice, VERDICTS } from '../labels';
import CameraModal from './CameraModal';
import Icon from './Icon';

/** Photo zone: preview + "Ouvrir la caméra" + "Importer" */
export function PhotoPicker({ value, onChange, hint = 'Photographiez ou importez l’article' }) {
  const [cameraOpen, setCameraOpen] = useState(false);
  const inputRef = useRef(null);

  const importFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (file) onChange(await resizeImage(file, 1024));
  };

  return (
    <div className="photo-picker">
      <div className={`photo-zone ${value ? 'has-photo' : ''}`}>
        {value ? (
          <>
            <img src={value} alt="Article" />
            <button className="icon-btn photo-remove" onClick={() => onChange(null)} aria-label="Retirer la photo">
              <Icon name="close" />
            </button>
          </>
        ) : (
          <div className="photo-empty">
            <Icon name="camera" size={34} strokeWidth={1.4} />
            <p>{hint}</p>
          </div>
        )}
      </div>
      <div className="photo-buttons">
        <button className="btn btn-primary" onClick={() => setCameraOpen(true)}>
          <Icon name="camera" /> Ouvrir la caméra
        </button>
        <button className="btn btn-ghost" onClick={() => inputRef.current?.click()}>
          <Icon name="upload" /> Importer
        </button>
        <input ref={inputRef} type="file" accept="image/*" hidden onChange={importFile} />
      </div>
      <CameraModal open={cameraOpen} onClose={() => setCameraOpen(false)} onCapture={onChange} />
    </div>
  );
}

export function Field({ label, children }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

export function Select({ value, onChange, options, placeholder }) {
  return (
    <select value={value || ''} onChange={(e) => onChange(e.target.value)}>
      {placeholder && <option value="">{placeholder}</option>}
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

export function ColorDot({ color }) {
  return <span className="color-dot" style={{ background: colorHex(color) }} title={colorLabel(color)} />;
}

/** Product / wardrobe card with image */
export function ItemCard({ item, badge, children, compact, onClick }) {
  const clickable = onClick ? {
    onClick, role: 'button', tabIndex: 0,
    onKeyDown: (e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onClick()),
  } : {};
  return (
    <article className={`item-card ${compact ? 'compact' : ''} ${onClick ? 'clickable' : ''}`} {...clickable}>
      <div className="item-image">
        <div className="item-placeholder" style={{ background: colorHex(item.color || item.primary_color), position: 'absolute', inset: 0 }} />
        {item.image_url && <img src={asset(item.image_url)} alt={item.name} loading="lazy" style={{ position: 'relative' }}
          onError={(e) => e.currentTarget.classList.add('broken')} />}
        {badge && <span className="item-badge">{badge}</span>}
      </div>
      <div className="item-body">
        <h4 title={item.name}>{item.name}</h4>
        <p className="item-meta">
          <ColorDot color={item.color || item.primary_color} />
          {categoryLabel(item.category)}
          {item.brand && <> · {item.brand}</>}
        </p>
        {(item.price || item.price === 0) && <p className="item-price">{formatPrice(item.price)}</p>}
        {children}
      </div>
    </article>
  );
}

/** Circular 0-100 score gauge */
export function ScoreRing({ value, tone = 'accent', label, size = 132 }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(100, value || 0));
  return (
    <div className={`score-ring tone-${tone}`} style={{ width: size, height: size }}>
      <svg viewBox="0 0 120 120">
        <circle cx="60" cy="60" r={r} className="ring-track" />
        <circle cx="60" cy="60" r={r} className="ring-value" strokeDasharray={c}
          strokeDashoffset={c * (1 - v / 100)} transform="rotate(-90 60 60)" />
      </svg>
      <div className="ring-label">
        <strong>{Math.round(v)}</strong>
        <span>{label}</span>
      </div>
    </div>
  );
}

export function VerdictPill({ verdict }) {
  const v = VERDICTS[verdict];
  if (!v) return null;
  return <span className={`pill pill-${v.tone}`}>{v.icon} {v.label}</span>;
}

export function Bar({ label, value, hint }) {
  const v = Math.max(0, Math.min(100, value || 0));
  return (
    <div className="bar-row">
      <div className="bar-head"><span>{label}</span><strong>{Math.round(v)}</strong></div>
      <div className="bar"><div style={{ width: `${v}%` }} /></div>
      {hint && <small>{hint}</small>}
    </div>
  );
}

export function Empty({ icon = 'hanger', title, children }) {
  return (
    <div className="empty-state">
      <Icon name={icon} size={36} strokeWidth={1.4} />
      <h3>{title}</h3>
      {children}
    </div>
  );
}
