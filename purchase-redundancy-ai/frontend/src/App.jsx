import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api, connectLive, errorMessage, session } from './api';
import { llmName } from './labels';
import { track } from './utils/analytics';
import Icon from './components/Icon';
import ErrorBoundary from './components/ErrorBoundary';
import AccountModal from './components/AccountModal';
import ProfileModal from './components/ProfileModal';
import StarterModal from './components/StarterModal';
import Scan from './pages/Scan';
import Agent from './pages/Agent';
import Wardrobe from './pages/Wardrobe';
import Catalog from './pages/Catalog';
import Dashboard from './pages/Dashboard';
import Studio from './pages/Studio';
import StyleProfile from './pages/StyleProfile';
import './App.css';

// Same navigation as the team's DressMe blueprint (pages that exist in this prototype)
const PAGES = [
  { id: 'stats', label: 'Tableau de bord', short: 'Accueil', icon: 'chart' },
  { id: 'wardrobe', label: 'Ma garde-robe', short: 'Garde-robe', icon: 'hanger' },
  { id: 'studio', label: 'Studio de tenues', short: 'Studio', icon: 'sparkle' },
  { id: 'scan', label: 'Dois-je l’acheter ?', short: 'Acheter ?', icon: 'scan' },
  { id: 'catalog', label: 'Trouver similaire', short: 'Similaire', icon: 'search' },
  { id: 'agent', label: 'Styliste IA', short: 'Styliste', icon: 'agent' },
  { id: 'profile', label: 'Profil de style', short: 'Profil', icon: 'user' },
];
const VERDICT_TEXT = { buy: 'Acheter', consider: 'À réfléchir', skip: 'Inutile' };

function readTheme() {
  try { return localStorage.getItem('doublon.theme'); } catch { return null; }
}

export default function App() {
  const [page, setPage] = useState('stats');
  const [wardrobe, setWardrobe] = useState([]);
  const [health, setHealth] = useState(null);
  const [stats, setStats] = useState(null);
  const [toast, setToast] = useState(null);
  const [offline, setOffline] = useState(false);
  const [user, setUser] = useState(null);
  const [authRequired, setAuthRequired] = useState(false);
  const [showAccount, setShowAccount] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [showStarter, setShowStarter] = useState(false);
  const [catalogPreset, setCatalogPreset] = useState(null);
  const [addRequest, setAddRequest] = useState(0);
  const [pending, setPending] = useState(0);
  const [theme, setTheme] = useState(readTheme);  // null = follow the system
  const [live, setLive] = useState(false);
  const [liveTick, setLiveTick] = useState(0);
  const lastLocalAnalysis = useRef(0);

  const notify = useCallback((text, tone = 'info') => {
    setToast({ text, tone, id: Date.now() });
  }, []);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = setTimeout(() => setToast(null), 4200);
    return () => clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    if (theme) document.documentElement.dataset.theme = theme;
    else delete document.documentElement.dataset.theme;
    try { if (theme) localStorage.setItem('doublon.theme', theme); else localStorage.removeItem('doublon.theme'); } catch { /* ignore */ }
  }, [theme]);

  const refreshWardrobe = useCallback(async () => {
    try {
      const { data } = await api.get('/wardrobe');
      setWardrobe(data.items);
    } catch (e) {
      if (e?.response?.status !== 401) notify(`Garde-robe indisponible : ${errorMessage(e)}`, 'bad');
    }
  }, [notify]);

  const refreshStatus = useCallback(async () => {
    try {
      const [h, s] = await Promise.all([api.get('/health'), api.get('/stats')]);
      setHealth(h.data);
      setStats(s.data);
      setOffline(false);
    } catch (e) {
      if (!e?.response) setOffline(true);
    }
  }, []);

  const refreshActions = useCallback(async () => {
    try {
      const { data } = await api.get('/agent/actions', { params: { status: 'pending' } });
      setPending(data.pending);
    } catch { /* the badge is optional */ }
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const { data } = await api.get('/auth/me');
      setUser(data.user);
      setAuthRequired(data.auth_required);
      if (data.auth_required && !data.user) setShowAccount(true);
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    refreshUser();
    refreshStatus();
    refreshWardrobe();
  }, [refreshUser, refreshStatus, refreshWardrobe]);
  useEffect(() => { refreshActions(); }, [refreshActions, user?.id, wardrobe.length]);

  // Session expired somewhere in the app -> back to the guest wardrobe
  useEffect(() => {
    const onExpired = () => {
      setUser(null);
      notify('Session expirée — reconnectez-vous pour retrouver votre garde-robe.', 'bad');
      refreshWardrobe();
      refreshStatus();
    };
    window.addEventListener('doublon:session-expired', onExpired);
    return () => window.removeEventListener('doublon:session-expired', onExpired);
  }, [notify, refreshWardrobe, refreshStatus]);

  // Real-time: another tab changed the wardrobe, made an analysis, or the agent acted
  useEffect(() => connectLive((event) => {
    if (event.type === 'wardrobe.changed') refreshWardrobe();
    if (event.type === 'agent.action') refreshActions();
    if (event.type === 'analysis.created') {
      refreshStatus();
      if (Date.now() - lastLocalAnalysis.current > 5000) {
        notify(`Nouvelle analyse : « ${event.data.name} » — ${VERDICT_TEXT[event.data.recommendation] || ''}`);
      }
    }
    if (event.type !== 'hello' && event.type !== 'pong') setLiveTick((t) => t + 1);
  }, setLive), [user, refreshWardrobe, refreshStatus, refreshActions, notify]);

  useEffect(() => { track('page_view', page); }, [page]);

  const addToWardrobe = useCallback(async (payload, label) => {
    try {
      const { data } = await api.post('/wardrobe', payload);
      await refreshWardrobe();
      notify(data.agent_alert
        ? `« ${label || data.name} » ajouté. L’agent a repéré un doublon : ${data.agent_alert.title}. Voir le Styliste IA.`
        : `« ${label || data.name} » ajouté à votre garde-robe`, data.agent_alert ? 'info' : 'good');
      if (data.agent_alert) refreshActions();
      track('wardrobe_add', page, { source: payload.product_id ? 'catalog' : payload.image_base64 ? 'photo' : 'form' });
      return data;
    } catch (e) {
      notify(errorMessage(e), 'bad');
      return null;
    }
  }, [notify, refreshWardrobe, refreshActions, page]);

  const onSignedIn = (signedUser, imported, starter) => {
    setUser(signedUser);
    setShowAccount(false);
    const parts = [`Bienvenue ${signedUser.display_name || ''} !`];
    if (starter?.added) parts.push(`Votre garde-robe de départ est prête : ${starter.added} pièces.`);
    if (imported?.wardrobe_items) parts.push(`${imported.wardrobe_items} pièce(s) transférée(s).`);
    notify(parts.join(' '), 'good');
    if (starter?.added) setPage('wardrobe');
    refreshWardrobe();
    refreshStatus();
  };

  const signOut = () => {
    session.clear();
    setUser(null);
    track('logout', page);
    notify('Déconnecté — vous utilisez la garde-robe invitée.');
    refreshWardrobe();
    refreshStatus();
    if (authRequired) setShowAccount(true);
  };

  const cycleTheme = () => setTheme((t) => (t === null ? 'dark' : t === 'dark' ? 'light' : null));
  const themeLabel = theme === 'dark' ? 'Thème sombre' : theme === 'light' ? 'Thème clair' : 'Thème du système';

  const ctx = {
    wardrobe, refreshWardrobe, addToWardrobe, notify, health, stats, refreshStatus, go: setPage, user, liveTick,
    pending, refreshActions, addRequest,
    markAnalysis: () => { lastLocalAnalysis.current = Date.now(); },
    openStarter: () => setShowStarter(true),
    openProfile: () => (user ? setShowProfile(true) : setShowAccount(true)),
    openAccount: () => setShowAccount(true),
    openCatalog: (preset) => { setCatalogPreset({ ...preset, at: Date.now() }); setPage('catalog'); },
    catalogPreset,
  };

  const initial = (user?.display_name || user?.email || 'Invité').trim()[0].toUpperCase();

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-word"><i>Dress</i><b>Me</b></span>
          <small>AI Style Intelligence</small>
        </div>
        <nav>
          {PAGES.map((p) => (
            <button key={p.id} className={`nav-item ${page === p.id ? 'active' : ''}`} onClick={() => setPage(p.id)}
              aria-current={page === p.id ? 'page' : undefined}>
              <Icon name={p.icon} size={18} />
              <span className="nav-label">{p.label}</span>
              <span className="nav-short">{p.short || p.label}</span>
              {p.id === 'wardrobe' && wardrobe.length > 0 && <em>{wardrobe.length}</em>}
              {p.id === 'agent' && pending > 0 && <em title="Propositions de l’agent en attente">{pending}</em>}
            </button>
          ))}
        </nav>
        <div className="sidebar-status">
          <button className="btn btn-add" onClick={() => { setPage('wardrobe'); setAddRequest(Date.now()); }}>
            <Icon name="plus" size={16} /> Ajouter une pièce
          </button>
          <div className="account-chip">
            {user ? (
              <>
                <button className="account-open" onClick={() => setPage('profile')} title="Profil de style">
                  <span className="avatar">{initial}</span>
                  <div><strong>{user.display_name || user.email}</strong><small>Profil de style</small></div>
                </button>
                <button className="icon-btn" onClick={signOut} aria-label="Se déconnecter" title="Se déconnecter"><Icon name="logout" size={16} /></button>
              </>
            ) : (
              <button className="account-open" onClick={() => setShowAccount(true)}>
                <span className="avatar">?</span>
                <div><strong>Invité</strong><small>Se connecter</small></div>
              </button>
            )}
          </div>
          <StatusLine ok={health?.llm?.available}
            label={health?.llm?.available ? `Agent ${llmName(health.llm)} actif` : 'Agent local (IA indisponible)'} />
          <StatusLine ok={health?.clip_available} label={health?.clip_available ? 'Vision CLIP active' : 'Vision simulée'} />
          <StatusLine ok={live} label={live ? 'Synchronisé en direct' : 'Reconnexion…'} />
          <button className="btn btn-ghost btn-sm theme-toggle" onClick={cycleTheme} aria-pressed={theme !== null} title={themeLabel}>
            <Icon name={theme === 'light' ? 'sun' : 'moon'} size={14} /> {themeLabel}
          </button>
        </div>
      </aside>

      <main className="content">
        <div className="mobile-bar">
          {user
            ? <button className="btn btn-ghost btn-sm" onClick={() => setShowProfile(true)}><Icon name="user" size={16} /> Mon compte</button>
            : <button className="btn btn-ghost btn-sm" onClick={() => setShowAccount(true)}><Icon name="user" size={16} /> Se connecter</button>}
          <button className="icon-btn theme-toggle" onClick={cycleTheme} aria-label={themeLabel} title={themeLabel}>
            <Icon name={theme === 'light' ? 'sun' : 'moon'} />
          </button>
        </div>
        {offline && (
          <div className="banner banner-bad">
            Le serveur ne répond pas. Lancez le backend (<code>python main.py</code>) puis
            <button className="link" onClick={refreshStatus}>réessayez</button>.
          </div>
        )}
        <ErrorBoundary resetKey={page}>
          {page === 'stats' && <Dashboard {...ctx} />}
          {page === 'wardrobe' && <Wardrobe {...ctx} />}
          {page === 'studio' && <Studio {...ctx} />}
          {page === 'scan' && <Scan {...ctx} />}
          {page === 'catalog' && <Catalog {...ctx} />}
          {page === 'agent' && <Agent {...ctx} />}
          {page === 'profile' && <StyleProfile {...ctx} />}
        </ErrorBoundary>
      </main>

      {showAccount && (
        <AccountModal guestItems={user ? 0 : wardrobe.length} onDone={onSignedIn}
          onClose={() => { if (!authRequired || user) setShowAccount(false); }} />
      )}
      {showProfile && user && (
        <ProfileModal user={user} notify={notify} onClose={() => setShowProfile(false)} onSaved={setUser}
          onStarter={() => setShowStarter(true)} onSignOut={signOut} />
      )}
      {showStarter && (
        <StarterModal user={user} notify={notify} onClose={() => setShowStarter(false)}
          onAdded={() => Promise.all([refreshWardrobe(), refreshStatus()])} />
      )}
      {toast && <div key={toast.id} className={`toast toast-${toast.tone}`} role="status">{toast.text}</div>}
    </div>
  );
}

function StatusLine({ ok, label }) {
  return (
    <div className="status-line">
      <span className={`dot ${ok ? 'dot-ok' : 'dot-off'}`} />
      {label}
    </div>
  );
}
