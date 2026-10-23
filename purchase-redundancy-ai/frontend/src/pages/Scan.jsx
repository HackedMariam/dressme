import React, { useState } from 'react';
import { api, errorMessage } from '../api';
import AnalysisHistory from '../components/AnalysisHistory';
import { track } from '../utils/analytics';
import Icon from '../components/Icon';
import { Bar, Field, ItemCard, PhotoPicker, ScoreRing, Select, VerdictPill } from '../components/ui';
import { CATEGORIES, COLORS, MATERIALS, STYLES, VERDICTS, categoryLabel, colorLabel, materialLabel, styleLabel } from '../labels';

const EMPTY = { name: '', category: '', color: '', style: 'casual', material: 'cotton', price: '' };

export default function Scan({ wardrobe, stats, addToWardrobe, notify, refreshStatus, go, markAnalysis }) {
  const [photo, setPhoto] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [detected, setDetected] = useState(null);
  const [detecting, setDetecting] = useState(false);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState(null);

  const set = (key) => (value) => setForm((f) => ({ ...f, [key]: value }));

  const onPhoto = async (dataUrl) => {
    setPhoto(dataUrl);
    setResult(null);
    setDetected(null);
    if (!dataUrl) return;
    setDetecting(true);
    try {
      const { data } = await api.post('/camera-capture', { image_base64: dataUrl });
      const attrs = data.analysis.attributes;
      setDetected({ ...attrs, colors: data.analysis.colors });
      const s = data.suggested_item;
      setForm((f) => ({
        ...f,
        category: s.category || f.category,
        color: s.color && s.color !== 'unknown' ? s.color : f.color,
        style: s.style || f.style,
        material: s.material || f.material,
        name: f.name || frenchName(s),
      }));
    } catch (e) {
      notify(`Analyse de la photo impossible : ${errorMessage(e)}`, 'bad');
    } finally {
      setDetecting(false);
    }
  };

  const analyze = async () => {
    if (!form.category) {
      notify('Choisissez une catégorie (ou prenez une photo)', 'bad');
      return;
    }
    setLoading(true);
    setFeedback(null);
    const price = parseFloat(form.price);
    const item = {
      ...form,
      name: form.name.trim() || frenchName(form),
      color: form.color || 'unknown',
      price: Number.isFinite(price) ? price : null,
    };
    try {
      markAnalysis?.();
      const { data } = await api.post('/analyze', { new_item: item, image_base64: photo, language: 'fr' });
      setResult(data);
      track('analysis_done', 'scan', { verdict: data.recommendation, with_photo: Boolean(photo), category: item.category });
      refreshStatus();
      setTimeout(() => document.getElementById('result')?.scrollIntoView({ behavior: 'smooth' }), 50);
    } catch (e) {
      notify(`Analyse impossible : ${errorMessage(e)}`, 'bad');
    } finally {
      setLoading(false);
    }
  };

  const sendFeedback = async (helpful) => {
    try {
      await api.post('/feedback', { item_id: result.analysis_id, feedback_type: helpful ? 'helpful' : 'inaccurate',
        rating: helpful ? 5 : 1, helped_decision: helpful });
      setFeedback(helpful ? 'up' : 'down');
    } catch (e) {
      notify(errorMessage(e), 'bad');
    }
  };

  const reset = () => { setPhoto(null); setForm(EMPTY); setDetected(null); setResult(null); };

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h2>Dois-je l’acheter ?</h2>
          <p>Photographiez l’article en magasin ou décrivez-le : il est comparé à vos {wardrobe.length} pièces avant que vous passiez en caisse.</p>
        </div>
        {(photo || result) && <button className="btn btn-ghost" onClick={reset}>Nouvel article</button>}
      </header>

      {wardrobe.length === 0 && (
        <div className="banner banner-warn">
          Votre garde-robe est vide : rien ne pourra être détecté comme doublon.
          <button className="link" onClick={() => go('wardrobe')}>Ajouter des pièces</button>
        </div>
      )}

      <section className="scan-grid card">
        <PhotoPicker value={photo} onChange={onPhoto} />

        <div className="scan-form">
          {detecting && <div className="detecting"><span className="spinner" /> La vision CLIP analyse la photo…</div>}
          {detected && !detecting && (
            <div className="detected">
              <span className="detected-title"><Icon name="sparkle" size={14} /> Détecté sur la photo</span>
              <div className="chips">
                <span className="chip">{categoryLabel(detected.category)} · {Math.round((detected.category_confidence || 0) * 100)}%</span>
                <span className="chip">{colorLabel(detected.primary_color)}</span>
                {detected.style && detected.style !== 'unknown' && <span className="chip">{styleLabel(detected.style)}</span>}
                {detected.material_appearance && detected.material_appearance !== 'unknown' &&
                  <span className="chip">aspect {materialLabel(detected.material_appearance)}</span>}
              </div>
            </div>
          )}

          <Field label="Nom de l’article">
            <input value={form.name} onChange={(e) => set('name')(e.target.value)} placeholder="ex. Chemise en lin bleu ciel" />
          </Field>
          <div className="form-row">
            <Field label="Catégorie"><Select value={form.category} onChange={set('category')} options={CATEGORIES} placeholder="Choisir…" /></Field>
            <Field label="Couleur"><Select value={form.color} onChange={set('color')} options={COLORS} placeholder="Choisir…" /></Field>
          </div>
          <div className="form-row">
            <Field label="Style"><Select value={form.style} onChange={set('style')} options={STYLES} /></Field>
            <Field label="Matière"><Select value={form.material} onChange={set('material')} options={MATERIALS} /></Field>
          </div>
          <Field label="Prix (optionnel)">
            <input type="number" min="0" value={form.price} onChange={(e) => set('price')(e.target.value)} placeholder="45" />
          </Field>

          <button className="btn btn-primary btn-lg btn-block" onClick={analyze} disabled={loading || detecting}>
            {loading ? <><span className="spinner" /> Analyse en cours…</> : <><Icon name="scan" /> Analyser</>}
          </button>
        </div>
      </section>

      {result && <Result result={result} photo={photo} feedback={feedback} onFeedback={sendFeedback}
        onBought={() => addToWardrobe({ ...result.new_item, image_base64: photo }, result.new_item.name)} />}
      <AnalysisHistory refreshKey={result?.analysis_id} />
    </div>
  );
}

function Result({ result, photo, feedback, onFeedback, onBought }) {
  const tone = VERDICTS[result.recommendation]?.tone || 'accent';
  const s = result.scores || {};
  return (
    <section id="result" className="result">
      <div className={`verdict-card tone-${tone}`}>
        <ScoreRing value={result.redundancy_score} tone={tone} label="redondance" />
        <div className="verdict-text">
          <VerdictPill verdict={result.recommendation} />
          <h3>{result.new_item.name}</h3>
          {result.warning?.warning_level !== 'none' && <p className="warning-text">{result.warning.message}</p>}
          <p className="muted">
            Confiance {Math.round(result.confidence * 100)}% · {result.embedding_mode?.startsWith('clip') ? 'vision CLIP' : 'mode simulé'}
            {photo && ' · photo comparée'} · {Math.round(result.execution_time_ms)} ms
          </p>
        </div>
        <div className="verdict-actions">
          <button className="btn btn-ghost" onClick={onBought}><Icon name="plus" /> Ajouter à ma garde-robe</button>
          <div className="feedback">
            <span>Utile ?</span>
            <button className={`icon-btn ${feedback === 'up' ? 'on' : ''}`} onClick={() => onFeedback(true)} aria-label="Utile"><Icon name="thumbUp" /></button>
            <button className={`icon-btn ${feedback === 'down' ? 'on' : ''}`} onClick={() => onFeedback(false)} aria-label="Pas utile"><Icon name="thumbDown" /></button>
          </div>
        </div>
      </div>

      <div className="result-grid">
        <div className="card">
          <h3>Pourquoi ?</h3>
          <p className="explanation">{result.explanation}</p>
          {result.explanation_source !== 'rules' && (
            <span className="tag">Rédigé par {result.explanation_source === 'openai' ? 'GPT' : 'Claude'}</span>
          )}
        </div>
        <div className="card">
          <h3>Détail du score</h3>
          <Bar label="Ressemblance visuelle" value={s.visual_similarity * 100} hint="40 % du score" />
          <Bar label="Même usage" value={s.functional_similarity} hint="30 %" />
          <Bar label="Catégorie déjà remplie" value={s.category_saturation} hint="20 %" />
          <Bar label="Nouvelles tenues apportées" value={s.outfit_contribution} hint="10 % (inversé)" />
        </div>
      </div>

      {result.similar_items.length > 0 && (
        <div className="card">
          <h3>Ce que vous avez déjà</h3>
          <div className="card-grid">
            {result.similar_items.map((item, i) => (
              <ItemCard key={item.id || i} item={item} badge={`${Math.round(item.similarity * 100)}%`}>
                {result.alternatives[i] && <p className="tip">💡 {result.alternatives[i].styling_tip}</p>}
              </ItemCard>
            ))}
          </div>
        </div>
      )}

      {result.catalog_matches?.length > 0 && (
        <div className="card">
          <h3>Modèles similaires sur le marché</h3>
          <div className="card-grid">
            {result.catalog_matches.map((item) => (
              <ItemCard key={item.id} item={item} compact badge={`${Math.round(item.similarity * 100)}%`} />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function frenchName(item) {
  const nouns = { shirts: 'Haut', pants: 'Pantalon', dresses: 'Robe', shoes: 'Chaussures', outerwear: 'Veste', accessories: 'Accessoire' };
  const noun = nouns[item.category] || 'Article';
  const color = item.color && item.color !== 'unknown' ? colorLabel(item.color).toLowerCase() : '';
  return [noun, color].filter(Boolean).join(' ');
}
