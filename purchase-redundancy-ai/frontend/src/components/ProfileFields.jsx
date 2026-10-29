import React, { useEffect, useState } from 'react';
import { api } from '../api';
import { CATEGORIES, CLOTHING_SIZES, COLORS, GENDERS, PROFILE_STYLES, SHOE_SIZES } from '../labels';
import { ColorDot, Field, Select } from './ui';

const MAX_STYLES = 5;
const MAX_COLORS = 8;

export const EMPTY_PROFILE = {
  gender: '', clothing_size: '', shoe_size: '', style_preferences: [], favorite_colors: [],
};

/** Profile payload for the API: empty values are left out */
export function profilePayload(profile) {
  return Object.fromEntries(Object.entries(profile).filter(([, v]) => (Array.isArray(v) ? v.length : v)));
}

/** Gender, sizes, preferred styles and colors - used by the sign-up form and the profile editor */
export default function ProfileFields({ value, onChange }) {
  const set = (key, v) => onChange({ ...value, [key]: v });
  const toggle = (key, item, max) => {
    const list = value[key] || [];
    if (list.includes(item)) set(key, list.filter((x) => x !== item));
    else if (list.length < max) set(key, [...list, item]);
  };

  return (
    <div className="profile-fields">
      <div className="field">
        <span>Je suis</span>
        <div className="segmented" role="radiogroup" aria-label="Sexe">
          {GENDERS.map((g) => (
            <button key={g.value} type="button" role="radio" aria-checked={value.gender === g.value}
              className={value.gender === g.value ? 'active' : ''} onClick={() => set('gender', g.value)}>{g.label}</button>
          ))}
        </div>
        <small className="muted">Adapte la garde-robe de départ et le catalogue (robes, talons, sacs… ou ceintures, montres…).</small>
      </div>

      <div className="form-row">
        <Field label="Taille de vêtements">
          <Select value={value.clothing_size} onChange={(v) => set('clothing_size', v)} options={CLOTHING_SIZES} placeholder="—" />
        </Field>
        <Field label="Pointure (EU)">
          <Select value={value.shoe_size} onChange={(v) => set('shoe_size', v)} options={SHOE_SIZES} placeholder="—" />
        </Field>
      </div>

      <div className="field">
        <span>Styles préférés <small className="muted">({(value.style_preferences || []).length}/{MAX_STYLES})</small></span>
        <div className="filter-chips">
          {PROFILE_STYLES.map((s) => {
            const on = (value.style_preferences || []).includes(s.value);
            return (
              <button key={s.value} type="button" aria-pressed={on} className={`chip chip-btn ${on ? 'active' : ''}`}
                onClick={() => toggle('style_preferences', s.value, MAX_STYLES)}>{s.label}</button>
            );
          })}
        </div>
      </div>

      <div className="field">
        <span>Couleurs préférées <small className="muted">({(value.favorite_colors || []).length}/{MAX_COLORS})</small></span>
        <div className="filter-chips">
          {COLORS.map((c) => {
            const on = (value.favorite_colors || []).includes(c.value);
            return (
              <button key={c.value} type="button" aria-pressed={on} className={`chip chip-btn color-chip ${on ? 'active' : ''}`}
                onClick={() => toggle('favorite_colors', c.value, MAX_COLORS)}>
                <ColorDot color={c.value} /> {c.label}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/** "≈ 50 pièces : 13 hauts, 10 bas…" - the starter wardrobe for a gender, from the API (single source of truth) */
export function StarterPreview({ gender }) {
  const [plan, setPlan] = useState(null);
  useEffect(() => {
    let alive = true;
    api.get('/wardrobe/starter-plan', { params: { gender: gender || 'Unspecified' } })
      .then((r) => alive && setPlan(r.data)).catch(() => alive && setPlan(null));
    return () => { alive = false; };
  }, [gender]);
  if (!plan) return null;
  return (
    <div className="starter-preview">
      <strong>{plan.total} pièces</strong>
      <ul>
        {CATEGORIES.filter((c) => plan.by_category[c.value]).map((c) => (
          <li key={c.value}><b>{plan.by_category[c.value]}</b> {c.label.toLowerCase()}</li>
        ))}
      </ul>
    </div>
  );
}
