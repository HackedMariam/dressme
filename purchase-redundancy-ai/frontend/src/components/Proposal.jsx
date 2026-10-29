import React, { useState } from 'react';
import { api, asset, errorMessage } from '../api';
import { track } from '../utils/analytics';
import Icon from './Icon';

const SOURCE = { watcher: 'Veille automatique', agent: 'Proposé par l’agent' };
const APPROVE = { remove_items: 'Retirer', duplicate_alert: 'Retirer la nouvelle pièce', add_items: 'Ajouter' };

/** An action the agent prepared (remove duplicates, add products) or flagged on its own - the user decides */
export default function Proposal({ action, notify, onDecided }) {
  const [state, setState] = useState(action);
  const [busy, setBusy] = useState(false);

  const decide = async (verb) => {
    setBusy(true);
    try {
      const { data } = await api.post(`/agent/actions/${state.id}/${verb}`);
      setState(data);
      track(`agent_action_${verb}`, 'agent', { kind: state.kind });
      if (verb === 'approve') {
        const r = data.result || {};
        notify(r.removed ? `Retiré : ${r.removed.join(', ')}` : r.added ? `Ajouté : ${r.added.join(', ')}` : 'Action effectuée', 'good');
      } else {
        notify('Proposition refusée — rien n’a changé.');
      }
      onDecided?.(data);
    } catch (e) {
      notify(errorMessage(e), 'bad');
    } finally {
      setBusy(false);
    }
  };

  const pieces = state.payload?.pieces || [];
  return (
    <div className={`proposal ${state.status}`}>
      <div className="proposal-head">
        <strong>{state.title}</strong>
        <span className="source-tag">{SOURCE[state.source] || 'Agent'}</span>
      </div>
      {state.detail && <p>{state.detail}</p>}
      {pieces.length > 0 && (
        <div className="proposal-pieces">
          {pieces.map((p) => <img key={p.id} src={asset(p.image_url)} alt={p.name} title={p.name} />)}
        </div>
      )}
      {state.status === 'pending' ? (
        <div className="proposal-actions">
          <button className="btn btn-primary btn-sm" onClick={() => decide('approve')} disabled={busy}>
            <Icon name="check" size={14} /> {APPROVE[state.kind] || 'Approuver'}
          </button>
          <button className="btn btn-ghost btn-sm" onClick={() => decide('reject')} disabled={busy}>
            {state.kind === 'duplicate_alert' ? 'Garder' : 'Refuser'}
          </button>
        </div>
      ) : (
        <p className="muted small">
          {state.status === 'done'
            ? `Fait${state.result?.removed ? ` — retiré : ${state.result.removed.join(', ')}` : state.result?.added ? ` — ajouté : ${state.result.added.join(', ')}` : ''}.`
            : 'Refusé — rien n’a changé.'}
        </p>
      )}
    </div>
  );
}
