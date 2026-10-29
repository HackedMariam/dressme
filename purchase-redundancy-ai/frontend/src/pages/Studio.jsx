import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { api, asset, errorMessage } from '../api';
import { track } from '../utils/analytics';
import Icon from '../components/Icon';
import { Empty, ScoreRing } from '../components/ui';
import { CATEGORIES, categoryLabel, colorLabel } from '../labels';

const OCCASIONS = [
  ['', 'Occasion…'], ['casual', 'Quotidien'], ['office', 'Bureau'], ['interview', 'Entretien'], ['date', 'Rendez-vous'],
  ['party', 'Soirée'], ['wedding', 'Mariage'], ['gym', 'Sport'], ['beach', 'Plage'],
];
const VERDICT = { excellent: 'Excellente association', good: 'Bonne association', weak: 'À compléter', empty: 'À composer' };

export default function Studio({ wardrobe, notify, go }) {
  const [mode, setMode] = useState('compose');
  if (!wardrobe.length) {
    return (
      <div className="page">
        <Header />
        <Empty icon="hanger" title="Votre garde-robe est vide"><button className="btn btn-primary" onClick={() => go('wardrobe')}>Ajouter des pièces</button></Empty>
      </div>
    );
  }
  return (
    <div className="page">
      <Header>
        <div className="segmented" role="tablist">
          <button role="tab" aria-selected={mode === 'compose'} className={mode === 'compose' ? 'active' : ''} onClick={() => setMode('compose')}>Composer une tenue</button>
          <button role="tab" aria-selected={mode === 'compare'} className={mode === 'compare' ? 'active' : ''} onClick={() => setMode('compare')}>Comparer deux pièces</button>
        </div>
      </Header>
      {mode === 'compose' ? <Compose wardrobe={wardrobe} notify={notify} /> : <Compare wardrobe={wardrobe} notify={notify} />}
    </div>
  );
}

function Header({ children }) {
  return (
    <header className="page-head">
      <div>
        <h2>Studio de tenues</h2>
        <p>Assemblez vos pièces : le moteur calcule la synergie de la tenue et vous conseille.</p>
      </div>
      {children}
    </header>
  );
}

function Compose({ wardrobe, notify }) {
  const [chosen, setChosen] = useState([]);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [result, setResult] = useState(null);
  const [name, setName] = useState('');
  const [occasion, setOccasion] = useState('');
  const [saved, setSaved] = useState([]);

  const byId = useMemo(() => Object.fromEntries(wardrobe.map((w) => [w.id, w])), [wardrobe]);
  const pieces = chosen.map((id) => byId[id]).filter(Boolean);
  const term = search.trim().toLowerCase();
  const list = wardrobe.filter((w) => (!category || w.category === category) && (!term || w.name.toLowerCase().includes(term)));

  const loadSaved = useCallback(() => api.get('/outfits').then((r) => setSaved(r.data.items)).catch(() => {}), []);
  useEffect(() => { loadSaved(); }, [loadSaved]);

  useEffect(() => {
    if (!chosen.length) { setResult(null); return undefined; }
    const timer = setTimeout(() => {
      api.post('/outfits/score', { item_ids: chosen }).then((r) => setResult(r.data)).catch((e) => notify(errorMessage(e), 'bad'));
    }, 250);
    return () => clearTimeout(timer);
  }, [chosen, notify]);

  const add = (id) => setChosen((c) => (c.includes(id) || c.length >= 10 ? c : [...c, id]));
  const remove = (id) => setChosen((c) => c.filter((x) => x !== id));

  const save = async () => {
    try {
      await api.post('/outfits', { name: name.trim() || 'Ma tenue', item_ids: chosen, occasion: occasion || undefined });
      notify('Tenue enregistrée', 'good');
      track('outfit_saved', 'studio', { pieces: chosen.length, score: result?.score });
      setName('');
      loadSaved();
    } catch (e) {
      notify(errorMessage(e), 'bad');
    }
  };

  const removeSaved = async (outfit) => {
    try {
      await api.delete(`/outfits/${outfit.id}`);
      loadSaved();
    } catch (e) {
      notify(errorMessage(e), 'bad');
    }
  };

  return (
    <>
      <div className="studio">
        <aside className="studio-panel">
          <span className="eyebrow-label">Votre garde-robe</span>
          <div className="studio-filters">
            <input className="studio-search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Rechercher…" aria-label="Rechercher une pièce" />
            <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Catégorie">
              <option value="">Toutes</option>
              {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
          </div>
          <div className="studio-list">
            {list.map((w) => (
              <button key={w.id} className="studio-item" onClick={() => add(w.id)} disabled={chosen.includes(w.id)}>
                <img src={asset(w.image_url)} alt="" />
                <div><strong>{w.name}</strong><small>{categoryLabel(w.category)} · {colorLabel(w.color)}</small></div>
                {!chosen.includes(w.id) && <span className="plus">+</span>}
              </button>
            ))}
          </div>
        </aside>

        <div className="studio-main">
          <section className="canvas">
            <div className="canvas-head">
              <span className="eyebrow-label">Tenue</span>
              {chosen.length > 0 && <button className="link" onClick={() => setChosen([])}>Tout retirer</button>}
            </div>
            {pieces.length === 0 ? (
              <div className="canvas-empty">
                <Icon name="sparkle" size={28} />
                <strong>Choisissez des pièces dans la liste</strong>
                <span className="small">Un haut, un bas, des chaussures… le score se calcule à chaque ajout.</span>
              </div>
            ) : (
              <div className="canvas-pieces">
                {pieces.map((p) => (
                  <div key={p.id} className="canvas-piece">
                    <img src={asset(p.image_url)} alt={p.name} />
                    <p title={p.name}>{p.name}</p>
                    <button onClick={() => remove(p.id)} aria-label={`Retirer ${p.name}`}>×</button>
                  </div>
                ))}
              </div>
            )}
          </section>

          {result && (
            <section className="night score-panel" aria-live="polite">
              <ScoreRing value={result.score} size={92} label="synergie" />
              <div>
                <span className="night-eyebrow">Score de synergie</span>
                <h3>{VERDICT[result.verdict]}</h3>
                <ul>{result.feedback.map((f) => <li key={f}>{f}</li>)}</ul>
                <div className="breakdown">
                  <span>Couleurs <b>{result.breakdown.harmony}</b></span>
                  <span>Complétude <b>{result.breakdown.completeness}</b></span>
                  <span>Style <b>{result.breakdown.coherence}</b></span>
                  <span>Saison <b>{result.breakdown.season}</b></span>
                </div>
              </div>
              {result.add?.length > 0 && (
                <div className="suggest-add">
                  <span className="night-eyebrow">Pour compléter</span>
                  {result.add.map((p) => (
                    <button key={p.id} onClick={() => add(p.id)}><img src={asset(p.image_url)} alt="" /> {p.name}</button>
                  ))}
                </div>
              )}
            </section>
          )}

          {pieces.length >= 2 && (
            <div className="save-row">
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nom de la tenue (ex. Lundi au bureau)" maxLength={120} aria-label="Nom de la tenue" />
              <select value={occasion} onChange={(e) => setOccasion(e.target.value)} aria-label="Occasion">
                {OCCASIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <button className="btn btn-dark" onClick={save}><Icon name="check" size={16} /> Enregistrer</button>
            </div>
          )}
        </div>
      </div>

      <section className="card">
        <h3>Mes tenues</h3>
        {saved.length === 0 ? <p className="muted">Aucune tenue enregistrée. Le Styliste IA peut aussi en enregistrer pour vous.</p> : (
          <div className="saved-looks">
            {saved.map((o) => (
              <div key={o.id} className="saved-look">
                <div className="saved-look-head">
                  <strong>{o.name}</strong>
                  {o.score != null && <span className="score-chip">{o.score}/100</span>}
                </div>
                <div className="thumbs">{o.pieces.map((p) => <img key={p.id} src={asset(p.image_url)} alt={p.name} title={p.name} />)}</div>
                <div className="proposal-actions">
                  {o.source === 'agent' && <span className="source-tag">Styliste IA</span>}
                  <button className="link" onClick={() => setChosen(o.pieces.map((p) => p.id))}>Ouvrir</button>
                  <button className="link danger-text" onClick={() => removeSaved(o)}>Supprimer</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  );
}

function Compare({ wardrobe, notify }) {
  const [a, setA] = useState(wardrobe[0]?.id || '');
  const [b, setB] = useState(wardrobe[1]?.id || '');
  const [result, setResult] = useState(null);
  const byId = Object.fromEntries(wardrobe.map((w) => [w.id, w]));

  const run = async () => {
    try {
      const { data } = await api.post('/wardrobe/compare', { item_a: a, item_b: b });
      setResult(data);
      track('pieces_compared', 'studio', { duplicate: data.duplicate });
    } catch (e) {
      notify(errorMessage(e), 'bad');
    }
  };
  useEffect(() => { setResult(null); }, [a, b]);

  const Slot = ({ value, onChange }) => (
    <div className="compare-slot">
      {byId[value] && <img src={asset(byId[value].image_url)} alt={byId[value].name} />}
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label="Pièce à comparer">
        {wardrobe.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
      </select>
    </div>
  );
  const pct = (v) => (v == null ? '—' : `${Math.round(v * 100)} %`);

  return (
    <section className="compare-grid">
      <Slot value={a} onChange={setA} />
      <div className="night compare-result">
        {result ? (
          <>
            <ScoreRing value={(result.similarity ?? result.visual_similarity) * 100} size={96} label="similarité" />
            <strong className="display" style={{ color: '#fff', fontSize: 18 }}>{result.duplicate ? 'Doublon probable' : 'Pièces différentes'}</strong>
            <div className="breakdown">
              <span>Visuel <b>{pct(result.visual_similarity)}</b></span>
              <span>Image <b>{pct(result.image_similarity)}</b></span>
              <span>Catégorie <b>{result.same_category ? 'oui' : 'non'}</b></span>
              <span>Couleur <b>{result.same_color ? 'oui' : 'non'}</b></span>
            </div>
          </>
        ) : (
          <>
            <span className="night-eyebrow">Vision CLIP</span>
            <p>Comparez deux pièces pour savoir si elles font double emploi.</p>
          </>
        )}
        <button className="btn btn-primary" onClick={run} disabled={!a || !b || a === b}>Comparer</button>
      </div>
      <Slot value={b} onChange={setB} />
    </section>
  );
}
