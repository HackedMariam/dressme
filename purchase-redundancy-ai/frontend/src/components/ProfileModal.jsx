import React, { useState } from 'react';
import { api, errorMessage } from '../api';
import Icon from './Icon';
import ProfileFields, { EMPTY_PROFILE } from './ProfileFields';
import { Field } from './ui';

/** Edit the account profile (name, gender, sizes, preferred styles and colors) */
export default function ProfileModal({ user, onClose, onSaved, onStarter, onSignOut, notify }) {
  const [name, setName] = useState(user.display_name || '');
  const [profile, setProfile] = useState({
    ...EMPTY_PROFILE,
    ...Object.fromEntries(Object.keys(EMPTY_PROFILE).map((k) => [k, user[k] ?? EMPTY_PROFILE[k]])),
  });
  const [busy, setBusy] = useState(false);

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      // null clears a field: the profile editor sends every field
      const payload = { display_name: name || null, ...Object.fromEntries(Object.entries(profile).map(([k, v]) =>
        [k, Array.isArray(v) ? v : v || null])) };
      const { data } = await api.patch('/auth/me', payload);
      onSaved(data.user);
      notify('Profil enregistré', 'good');
      onClose();
    } catch (err) {
      notify(errorMessage(err), 'bad');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <form className="modal account-modal wide" onClick={(e) => e.stopPropagation()} onSubmit={save} role="dialog" aria-label="Mon profil">
        <header className="modal-head">
          <h3>Mon profil</h3>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Fermer"><Icon name="close" /></button>
        </header>
        <div className="modal-body account-body">
          <p className="muted small">{user.email}</p>
          <Field label="Prénom et nom">
            <input value={name} onChange={(e) => setName(e.target.value)} maxLength={100} autoComplete="name" />
          </Field>
          <ProfileFields value={profile} onChange={setProfile} />
          <div className="profile-actions">
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => { onClose(); onStarter(); }}>
              <Icon name="sparkle" size={16} /> Ajouter ma garde-robe de départ
            </button>
            <button type="button" className="btn btn-ghost btn-sm danger-text" onClick={() => { onClose(); onSignOut(); }}>
              <Icon name="logout" size={16} /> Se déconnecter
            </button>
          </div>
        </div>
        <footer className="modal-foot">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Annuler</button>
          <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? <span className="spinner" /> : 'Enregistrer'}</button>
        </footer>
      </form>
    </div>
  );
}
