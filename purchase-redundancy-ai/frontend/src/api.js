import axios from 'axios';

// '/api' goes through the Vite dev proxy (vite.config.js). Set VITE_API_URL to call the backend directly.
export const API_BASE = import.meta.env.VITE_API_URL || '/api';
// Optional CDN for the catalog images (they never change for a given id): VITE_CDN_URL=https://cdn.example.com
const CDN_BASE = (import.meta.env.VITE_CDN_URL || '').replace(/\/$/, '');
export const api = axios.create({ baseURL: API_BASE, timeout: 180000 });

// ---------- session (JWT in localStorage; no token = guest wardrobe) ----------

const TOKEN_KEY = 'doublon.token';

export const session = {
  get() {
    try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
  },
  set(token) {
    try { localStorage.setItem(TOKEN_KEY, token); } catch { /* private mode: session lasts until reload */ }
    memoryToken = token;
  },
  clear() {
    try { localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
    memoryToken = null;
  },
};
let memoryToken = null;
const currentToken = () => session.get() || memoryToken;

export function authHeaders() {
  const token = currentToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

api.interceptors.request.use((config) => {
  Object.assign(config.headers, authHeaders());
  return config;
});

api.interceptors.response.use((response) => response, (error) => {
  // Expired / revoked token: fall back to the guest session and tell the app
  if (error?.response?.status === 401 && currentToken() && !String(error.config?.url).startsWith('/auth/')) {
    session.clear();
    window.dispatchEvent(new CustomEvent('doublon:session-expired'));
  }
  return Promise.reject(error);
});

/** Backend-relative image URLs (/images/..., /uploads/...) -> loadable URL */
export function asset(url) {
  if (!url) return null;
  if (url.startsWith('http') || url.startsWith('data:') || url.startsWith('blob:')) return url;
  if (CDN_BASE && url.startsWith('/images/')) return `${CDN_BASE}${url}`;
  return `${API_BASE}${url}`;
}

/** WebSocket to /ws/live with automatic reconnection (1 s -> 30 s backoff). Returns a close() function. */
export function connectLive(onEvent, onStatus) {
  let socket = null;
  let closed = false;
  let delay = 1000;
  let pingTimer = null;

  const url = () => {
    const base = API_BASE.startsWith('http')
      ? API_BASE.replace(/^http/, 'ws')
      : `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}${API_BASE}`;
    const token = currentToken();
    return `${base}/ws/live${token ? `?token=${encodeURIComponent(token)}` : ''}`;
  };

  const open = () => {
    if (closed) return;
    socket = new WebSocket(url());
    socket.onopen = () => {
      delay = 1000;
      onStatus?.(true);
      pingTimer = setInterval(() => socket?.readyState === 1 && socket.send('ping'), 25000);
    };
    socket.onmessage = (message) => {
      try { onEvent(JSON.parse(message.data)); } catch { /* ignore malformed frames */ }
    };
    socket.onclose = () => {
      clearInterval(pingTimer);
      onStatus?.(false);
      if (!closed) setTimeout(open, delay);
      delay = Math.min(delay * 2, 30000);
    };
  };
  open();
  return () => { closed = true; clearInterval(pingTimer); socket?.close(); };
}

export function errorMessage(error) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join(', ');
  return error?.message || 'Erreur inconnue';
}

/** POST /agent/run and call onEvent for every NDJSON event as it arrives */
export async function streamAgent(payload, onEvent, signal) {
  const response = await fetch(`${API_BASE}/agent/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(payload),
    signal,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).detail || detail; } catch { /* not JSON */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let index;
    while ((index = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, index).trim();
      buffer = buffer.slice(index + 1);
      if (line) onEvent(JSON.parse(line));
    }
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer));
}

/** File / Blob / canvas -> JPEG data URL, longest side <= max (keeps uploads small) */
export function resizeImage(source, max = 1024) {
  return new Promise((resolve, reject) => {
    const draw = (img, w, h) => {
      const scale = Math.min(1, max / Math.max(w, h));
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(w * scale);
      canvas.height = Math.round(h * scale);
      canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
      resolve(canvas.toDataURL('image/jpeg', 0.88));
    };
    if (source instanceof HTMLCanvasElement) {
      draw(source, source.width, source.height);
      return;
    }
    const url = URL.createObjectURL(source);
    const img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); draw(img, img.naturalWidth, img.naturalHeight); };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Impossible de lire l'image")); };
    img.src = url;
  });
}
