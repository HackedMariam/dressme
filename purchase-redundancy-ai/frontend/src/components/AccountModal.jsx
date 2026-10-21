import React, { useState } from 'react';
import { api, errorMessage, session } from '../api';
import { track } from '../utils/analytics';
import Icon from './Icon';
import ProfileFields, { EMPTY_PROFILE, StarterPreview, profilePayload } from './ProfileFields';
import { Field } from './ui';

/** Sign in / create an account (with profile and starter wardrobe). onDone(user, imported, starter) after success. */
export default function AccountModal({ onClose, onDone, guestItems = 0 }) {
  const [mode, setMode] = useState('login');
  const [form, setForm] = useState({ email: '', password: '', display_name: '' });
  const [profile, setProfile] = useState(EMPTY_PROFILE);
  const [starter, setStarter] = useState(true);
  const [importGuest, setImportGuest] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const registering = mode === 'register';

  const submit = async (e) => {
    e.preventDefault();
    if (registering && !profile.gender) {
      setError('Indiquez si vous êtes une femme, un homme, ou « Non précisé ».');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const payload = registering
        ? { email: form.email, password: form.password, display_name: form.display_name || undefined,
            ...profilePayload(profile), starter_wardrobe: starter, import_guest_data: importGuest }
        : { email: form.email, password: form.password };
      const { data } = await api.post(registering ? '/auth/register' : '/auth/login', payload);
      session.set(data.access_token);
      track(registering ? 'signup' : 'login', 'account',
        registering ? { gender: profile.gender, starter, imported: importGuest } : undefined);
      onDone(data.user, data.imported, data.starter);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <form className={`modal account-modal ${registering ? 'wide' : ''}`} onClick={(e) => e.stopPropagation()} onSubmit={submit}
        role="dialog" aria-label={registering ? 'Créer un compte' : 'Connexion'}>
        <header className="modal-head">
          <h3>{registering ? 'Créer un compte' : 'Connexion'}</h3>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Fermer"><Icon name="close" /></button>
        </header>
        <div className="modal-body account-body">
          <div className="segmented" role="tablist">
            <button type="button" role="tab" aria-selected={!registering} className={!registering ? 'active' : ''}
              onClick={() => { setMode('login'); setError(''); }}>J’ai un compte</button>
            <button type="button" role="tab" aria-selected={registering} className={registering ? 'active' : ''}
              onClick={() => { setMode('register'); setError(''); }}>Nouveau compte</button>
          </div>

          {!registering && (
            <p className="muted small">
              Un compte garde votre garde-robe et votre historique privés, sur tous vos appareils.
              Sans compte, vous utilisez la garde-robe invitée de cet ordinateur.
            </p>
          )}

          <section className="form-section">
            {registering && <h4>1. Mon compte</h4>}
            {registering && (
              <Field label="Prénom et nom (optionnel)">
                <input value={form.display_name} onChange={set('display_name')} maxLength={100} autoComplete="name" />
              </Field>
            )}
            <div className={registering ? 'form-row' : ''}>
              <Field label="E-mail">
                <input type="email" required value={form.email} onChange={set('email')} autoComplete="email" maxLength={255} />
              </Field>
              <Field label="Mot de passe">
                <input type="password" required value={form.password} onChange={set('password')} minLength={registering ? 8 : 1}
                  maxLength={128} autoComplete={registering ? 'new-password' : 'current-password'} />
              </Field>
            </div>
            {registering && <p className="muted small">8 caractères minimum, avec lettres et chiffres.</p>}
          </section>

          {registering && (
            <>
              <section className="form-section">
                <h4>2. Mon profil</h4>
                <ProfileFields value={profile} onChange={setProfile} />
              </section>

              <section className="form-section">
                <h4>3. Ma garde-robe</h4>
                <label className="check-line starter-option">
                  <input type="checkbox" checked={starter} onChange={(e) => setStarter(e.target.checked)} />
                  <span>
                    <strong>Créer ma garde-robe de départ</strong> — de vrais vêtements, chaussures et accessoires
                    {profile.gender === 'Women' ? ' pour femme' : profile.gender === 'Men' ? ' pour homme' : ''}, choisis selon vos
                    styles et couleurs, à vos tailles. Retirez ensuite ce que vous ne possédez pas.
                  </span>
                </label>
                {starter && <StarterPreview gender={profile.gender} />}
                {guestItems > 0 && (
                  <label className="check-line">
                    <input type="checkbox" checked={importGuest} onChange={(e) => setImportGuest(e.target.checked)} />
                    Transférer aussi ma garde-robe actuelle ({guestItems} pièce{guestItems > 1 ? 's' : ''}) et mon historique
                  </label>
                )}
              </section>
            </>
          )}
          {error && <p className="form-error" role="alert">{error}</p>}
        </div>
        <footer className="modal-foot">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Annuler</button>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? <><span className="spinner" /> {registering && starter ? 'Création de votre garde-robe…' : 'Un instant…'}</>
              : registering ? 'Créer mon compte' : 'Se connecter'}
          </button>
        </footer>
      </form>
    </div>
  );
}
