import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api, connectLive, errorMessage, session } from './api';
import { llmName } from './labels';
import { track } from './utils/analytics';
import Icon from './components/Icon';
import ErrorBoundary from './components/ErrorBoundary';
import AccountModal from './components/AccountModal';
import ProfileModal from './components/ProfileModal';
import StarterModal from './components/StarterModal';
import Home from './pages/Home';
import Scan from './pages/Scan';
import Agent from './pages/Agent';
import Wardrobe from './pages/Wardrobe';
import Catalog from './pages/Catalog';
import Dashboard from './pages/Dashboard';
import './App.css';

const PAGES = [
  { id: 'home', label: 'Accueil', icon: 'home' },
  { id: 'scan', label: 'Analyser', icon: 'scan' },
  { id: 'wardrobe', label: 'Garde-robe', icon: 'hanger' },
  { id: 'stats', label: 'Tableau de bord', short: 'Bilan', icon: 'chart' },
  { id: 'agent', label: 'Conseiller IA', short: 'Conseiller', icon: 'agent' },
  { id: 'catalog', label: 'Catalogue', icon: 'grid' },
];
const VERDICT_TEXT = { buy: 'Acheter', consider: 'À réfléchir', skip: 'Inutile' };

function readTheme() {
  try { return localStorage.getItem('doublon.theme'); } catch { return null; }
}

export default function App() {
  const [page, setPage] = useState('home');
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
  const [theme, setTheme] = useState(readTheme);  // null = follow the system
  const [live, setLive] = useState(false);
  const [liveTick, setLiveTick] = useState(0);
  const lastLocalAnalysis = useRef(0);

  const notify = useCallback((text, tone = 'info') => {
    setToast({ text, tone, id: Date.now() });
  }, []);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = setTimeout(() => setToast(null), 3800);
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

  // Real-time: another tab or device changed this wardrobe or made an analysis
  useEffect(() => connectLive((event) => {
    if (event.type === 'wardrobe.changed') refreshWardrobe();
    if (event.type === 'analysis.created') {
      refreshStatus();
      if (Date.now() - lastLocalAnalysis.current > 5000) {
        notify(`Nouvelle analyse : « ${event.data.name} » — ${VERDICT_TEXT[event.data.recommendation] || ''}`);
      }
    }
    if (event.type !== 'hello' && event.type !== 'pong') setLiveTick((t) => t + 1);
  }, setLive), [user, refreshWardrobe, refreshStatus, notify]);

  useEffect(() => { track('page_view', page); }, [page]);

  const addToWardrobe = useCallback(async (payload, label) => {
    try {
      const { data } = await api.post('/wardrobe', payload);
      await refreshWardrobe();
      notify(`« ${label || data.name} » ajouté à votre garde-robe`, 'good');
      track('wardrobe_add', page, { source: payload.product_id ? 'catalog' : payload.image_base64 ? 'photo' : 'form' });
      return data;
    } catch (e) {
      notify(errorMessage(e), 'bad');
      return null;
    }
  }, [notify, refreshWardrobe, page]);

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
    markAnalysis: () => { lastLocalAnalysis.current = Date.now(); },
    openStarter: () => setShowStarter(true),
    openProfile: () => (user ? setShowProfile(true) : setShowAccount(true)),
    openCatalog: (preset) => { setCatalogPreset({ ...preset, at: Date.now() }); setPage('catalog'); },
    catalogPreset,
  };

  const accountControls = (
    <div className="account-box">
      {user ? (
        <div className="account-chip">
          <button className="account-open" onClick={() => setShowProfile(true)} title="Mon profil">
            <Icon name="user" />
            <div><strong>{user.display_name || user.email}</strong><small>Mon profil · {user.email}</small></div>
          </button>
          <button className="icon-btn" onClick={signOut} aria-label="Se déconnecter" title="Se déconnecter"><Icon name="logout" size={16} /></button>
        </div>
      ) : (
        <button className="btn btn-ghost btn-sm" onClick={() => setShowAccount(true)}><Icon name="user" size={16} /> Se connecter</button>
      )}
      <div className="sidebar-actions">
        <button className="btn btn-ghost btn-sm theme-toggle" onClick={cycleTheme} aria-pressed={theme !== null} title={themeLabel}>
          <Icon name={theme === 'light' ? 'sun' : 'moon'} size={16} /> {themeLabel}
        </button>
      </div>
    </div>
  );

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">◐</span>
          <div>
            <strong>Doublon</strong>
            <small>Anti-achat inutile</small>
          </div>
        </div>
        <nav>
          {PAGES.map((p) => (
            <button key={p.id} className={`nav-item ${page === p.id ? 'active' : ''}`} onClick={() => setPage(p.id)}
              aria-current={page === p.id ? 'page' : undefined}>
              <Icon name={p.icon} size={20} />
              <span className="nav-label">{p.label}</span>
              <span className="nav-short">{p.short || p.label}</span>
              {p.id === 'wardrobe' && wardrobe.length > 0 && <em>{wardrobe.length}</em>}
            </button>
          ))}
        </nav>
        <div className="sidebar-status">
          <StatusLine ok={health?.clip_available} label={health?.clip_available ? 'Vision CLIP active' : 'Vision simulée'} />
          <StatusLine ok={health?.llm?.available}
            label={health?.llm?.available ? `${llmName(health.llm)} connecté` : 'Agent local (IA indisponible)'} />
          <StatusLine ok={live} label={live ? 'Synchronisation en direct' : 'Hors ligne (reconnexion…)'} />
          {accountControls}
        </div>
      </aside>

      <main className="content">
        <div className="mobile-bar">
          {user
            ? <button className="btn btn-ghost btn-sm" onClick={() => setShowProfile(true)}><Icon name="user" size={16} /> Mon profil</button>
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
          {page === 'home' && <Home {...ctx} />}
          {page === 'scan' && <Scan {...ctx} />}
          {page === 'agent' && <Agent {...ctx} />}
          {page === 'wardrobe' && <Wardrobe {...ctx} />}
          {page === 'catalog' && <Catalog {...ctx} />}
          {page === 'stats' && <Dashboard {...ctx} />}
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
