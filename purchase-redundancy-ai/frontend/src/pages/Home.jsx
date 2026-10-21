import React, { useEffect, useState } from 'react';
import { api, asset } from '../api';
import Icon from '../components/Icon';
import { ScoreRing, VerdictPill } from '../components/ui';
import { formatPrice } from '../labels';

export default function Home({ wardrobe, stats, go, openStarter, liveTick }) {
  const [history, setHistory] = useState([]);
  const [report, setReport] = useState(null);

  useEffect(() => {
    if (!wardrobe.length) return;
    api.get('/insights').then((r) => setReport(r.data)).catch(() => setReport(null));
  }, [wardrobe.length, liveTick]);

  useEffect(() => {
    api.get('/analyses', { params: { limit: 6 } }).then((r) => setHistory(r.data.items)).catch(() => setHistory([]));
  }, [stats?.analyses_run]);

  const catalogSize = stats?.products_in_catalog;

  return (
    <div className="page">
      <section className="hero">
        <div className="hero-text">
          <span className="eyebrow">Avant de passer en caisse</span>
          <h1>Vous l’avez peut-être <em>déjà</em>.</h1>
          <p>
            Prenez l’article en photo : il est comparé à votre garde-robe
            {catalogSize ? ` et à ${catalogSize} vrais produits` : ''}, puis le conseiller IA vous dit s’il vaut vraiment le coup.
          </p>
          <div className="hero-actions">
            <button className="btn btn-primary btn-lg" onClick={() => go('scan')}>
              <Icon name="camera" /> Scanner un article
            </button>
            <button className="btn btn-ghost btn-lg" onClick={() => go('agent')}>
              <Icon name="agent" /> Demander au conseiller
            </button>
          </div>
        </div>
        <div className="hero-visual" aria-hidden="true">
          {wardrobe.slice(0, 4).map((item, i) => (
            <img key={item.id} src={asset(item.image_url)} alt="" className={`hero-card hero-card-${i}`} />
          ))}
          {wardrobe.length === 0 && <div className="hero-placeholder"><Icon name="hanger" size={64} strokeWidth={1.2} /></div>}
        </div>
      </section>

      {report && !report.empty && (
        <section className="card summary-card">
          <ScoreRing value={report.health} tone={report.health >= 75 ? 'good' : report.health >= 50 ? 'warn' : 'bad'} size={92} label="santé" />
          <div className="summary-main">
            <div className="section-head">
              <h3>Mon bilan</h3>
              <button className="link" onClick={() => go('stats')}>Tableau de bord <Icon name="arrow" size={14} /></button>
            </div>
            <p className="muted small">
              {wardrobe.length} pièces · {stats?.analyses_run ?? 0} achats analysés · {stats?.duplicates_avoided ?? 0} doublons évités
              {stats?.money_saved > 0 && <> · {formatPrice(stats.money_saved)} économisés</>}
            </p>
            <ul className="summary-tips">
              {report.tips.slice(0, 2).map((t) => <li key={t.id} className={`sev-${t.severity}`}><strong>{t.title}</strong> — {t.detail}</li>)}
            </ul>
          </div>
        </section>
      )}

      {wardrobe.length === 0 ? (
        <section className="card callout">
          <div>
            <h3>Commencez par votre garde-robe</h3>
            <p>Photographiez vos vêtements, choisissez-les dans le catalogue, ou ajoutez une garde-robe de départ de 40+ pièces adaptée (femme, homme ou mixte).</p>
          </div>
          <div className="callout-actions">
            <button className="btn btn-ghost" onClick={() => go('wardrobe')}><Icon name="plus" /> Ajouter mes pièces</button>
            <button className="btn btn-primary" onClick={openStarter}>
              <Icon name="sparkle" /> Garde-robe de départ
            </button>
          </div>
        </section>
      ) : (
        <section className="card">
          <div className="section-head">
            <h3>Votre garde-robe</h3>
            <button className="link" onClick={() => go('wardrobe')}>Tout voir <Icon name="arrow" size={14} /></button>
          </div>
          <div className="thumb-strip">
            {wardrobe.slice(0, 12).map((item) => (
              <figure key={item.id}>
                <img src={asset(item.image_url)} alt={item.name} />
                <figcaption>{item.name}</figcaption>
              </figure>
            ))}
          </div>
        </section>
      )}

      <section className="card">
        <div className="section-head">
          <h3>Dernières analyses</h3>
          <button className="link" onClick={() => go('scan')}>Analyser un article <Icon name="arrow" size={14} /></button>
        </div>
        {history.length === 0 ? (
          <p className="muted">Aucune analyse pour l’instant — scannez votre premier article.</p>
        ) : (
          <ul className="history">
            {history.map((h) => (
              <li key={h.analysis_id}>
                {h.image_url ? <img src={asset(h.image_url)} alt="" /> : <span className="history-icon"><Icon name="scan" /></span>}
                <div className="history-main">
                  <strong>{h.name}</strong>
                  <span className="muted small">
                    {h.top_match ? `Proche de « ${h.top_match} »` : 'Rien de similaire'} · {formatDate(h.created_at)}
                  </span>
                </div>
                <span className="history-score">{Math.round(h.redundancy_score)}</span>
                <VerdictPill verdict={h.recommendation} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

/** "21 oct., 22:34" - the API stores naive UTC timestamps */
function formatDate(iso) {
  if (!iso) return '';
  const date = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
  return date.toLocaleString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}
