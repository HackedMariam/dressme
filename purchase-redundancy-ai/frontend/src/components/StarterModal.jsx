import React, { useState } from 'react';
import { api, errorMessage } from '../api';
import { track } from '../utils/analytics';
import { CATEGORIES, GENDERS } from '../labels';
import Icon from './Icon';
import { StarterPreview } from './ProfileFields';

/** Add a starter wardrobe (40+ real pieces) for a gender - nothing already owned is removed */
export default function StarterModal({ user, onClose, onAdded, notify }) {
  const [gender, setGender] = useState(user?.gender || 'Unspecified');
  const [busy, setBusy] = useState(false);

  const add = async () => {
    setBusy(true);
    try {
      const { data } = await api.post('/wardrobe/sample', null, { params: { gender } });
      const detail = CATEGORIES.filter((c) => data.by_category[c.value])
        .map((c) => `${data.by_category[c.value]} ${c.label.toLowerCase()}`).join(', ');
      notify(`${data.added} pièces ajoutées (${detail}) — vos pièces sont conservées`, 'good');
      track('starter_wardrobe', 'wardrobe', { gender, added: data.added });
      await onAdded();
      onClose();
    } catch (e) {
      notify(errorMessage(e), 'bad');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div className="modal account-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Garde-robe de départ">
        <header className="modal-head">
          <h3>Garde-robe de départ</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Fermer"><Icon name="close" /></button>
        </header>
        <div className="modal-body account-body">
          <p className="muted small">
            Ajoute d’un coup une garde-robe complète de vrais produits : hauts, bas, chaussures et accessoires adaptés.
            {user?.style_preferences?.length ? ' Elle suit vos styles et couleurs préférés.' : ''} Rien n’est supprimé ;
            retirez ensuite ce que vous ne possédez pas.
          </p>
          <div className="field">
            <span>Pour</span>
            <div className="segmented" role="radiogroup" aria-label="Pour">
              {GENDERS.map((g) => (
                <button key={g.value} type="button" role="radio" aria-checked={gender === g.value}
                  className={gender === g.value ? 'active' : ''} onClick={() => setGender(g.value)}>
                  {g.value === 'Unspecified' ? 'Mixte' : g.label}
                </button>
              ))}
            </div>
          </div>
          <StarterPreview gender={gender} />
        </div>
        <footer className="modal-foot">
          <button className="btn btn-ghost" onClick={onClose}>Annuler</button>
          <button className="btn btn-primary" onClick={add} disabled={busy}>
            {busy ? <><span className="spinner" /> Ajout en cours…</> : <><Icon name="sparkle" /> Ajouter à ma garde-robe</>}
          </button>
        </footer>
      </div>
    </div>
  );
}
