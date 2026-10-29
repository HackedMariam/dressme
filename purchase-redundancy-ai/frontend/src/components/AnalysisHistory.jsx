import React, { useEffect, useState } from 'react';
import { api, asset } from '../api';
import Icon from './Icon';
import { VerdictPill } from './ui';

/** The last purchase decisions ("Dois-je l'acheter ?" history) */
export default function AnalysisHistory({ refreshKey }) {
  const [history, setHistory] = useState([]);
  useEffect(() => {
    api.get('/analyses', { params: { limit: 8 } }).then((r) => setHistory(r.data.items)).catch(() => setHistory([]));
  }, [refreshKey]);

  return (
    <section className="card">
      <h3>Dernières décisions</h3>
      {history.length === 0 ? (
        <p className="muted">Aucune analyse pour l’instant — analysez votre premier article ci-dessus.</p>
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
  );
}

/** "21 oct., 22:34" - the API stores naive UTC timestamps */
function formatDate(iso) {
  if (!iso) return '';
  const date = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
  return date.toLocaleString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}
