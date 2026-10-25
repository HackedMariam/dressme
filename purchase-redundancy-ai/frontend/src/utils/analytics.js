import { API_BASE, authHeaders } from '../api';

// Product analytics: page views and key actions, batched to POST /analytics/events.
// No personal data is sent (no names, photos, emails or free text) and "Do Not Track" is honored.

const FLUSH_MS = 5000;
const MAX_BATCH = 20;
const queue = [];
let timer = null;

const disabled = typeof navigator !== 'undefined'
  && (navigator.doNotTrack === '1' || window.doNotTrack === '1');

function sessionId() {
  try {
    let id = sessionStorage.getItem('doublon.session');
    if (!id) {
      id = (crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`).slice(0, 36);
      sessionStorage.setItem('doublon.session', id);
    }
    return id;
  } catch {
    return undefined;
  }
}

function flush() {
  clearTimeout(timer);
  timer = null;
  if (!queue.length) return;
  const events = queue.splice(0, MAX_BATCH);
  // keepalive lets the last batch leave while the tab closes
  fetch(`${API_BASE}/analytics/events`, {
    method: 'POST',
    keepalive: true,
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ session_id: sessionId(), events }),
  }).catch(() => { /* analytics must never disturb the user */ });
  if (queue.length) timer = setTimeout(flush, FLUSH_MS);
}

/** track('camera_open', 'scan', { source: 'button' }) - properties must be flat scalars */
export function track(name, page, properties) {
  if (disabled) return;
  queue.push({ name, ...(page ? { page } : {}), ...(properties ? { properties } : {}) });
  if (queue.length >= MAX_BATCH) flush();
  else if (!timer) timer = setTimeout(flush, FLUSH_MS);
}

if (typeof window !== 'undefined') {
  window.addEventListener('pagehide', flush);
  document.addEventListener('visibilitychange', () => document.visibilityState === 'hidden' && flush());
}
