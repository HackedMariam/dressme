import { supabase } from './supabase'

export const API = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

async function req(path, opts = {}) {
  const headers = { ...(opts.headers || {}) }
  if (supabase) {
    const { data } = await supabase.auth.getSession()
    if (data.session) headers.Authorization = `Bearer ${data.session.access_token}`
  }
  let r
  try {
    r = await fetch(API + path, { ...opts, headers })
  } catch {
    throw new ApiError(`Cannot reach the server at ${API}`, 0)
  }
  if (r.status === 401 && supabase) await supabase.auth.signOut()
  if (!r.ok) {
    let msg = r.statusText
    try { msg = (await r.json()).detail || msg } catch {}
    throw new ApiError(typeof msg === 'string' ? msg : 'Request failed', r.status)
  }
  return r.json()
}

export const api = {
  health: () => req('/api/health'),
  list: () => req('/api/items'),
  analyze: (file, allItems = false, fast = false) => {
    const fd = new FormData()
    fd.append('file', file)
    return req(`/api/items/analyze?all_items=${allItems}&fast=${fast}`, { method: 'POST', body: fd })
  },
  quickDetect: (blob) => {
    const fd = new FormData()
    fd.append('file', blob, 'frame.jpg')
    return req('/api/items/quick-detect', { method: 'POST', body: fd })
  },
  update: (id, fields, confirm = true) =>
    req(`/api/items/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fields, confirm }),
    }),
  reclassify: (id) => req(`/api/items/${id}/reclassify`, { method: 'POST' }),
  searchByPhoto: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return req('/api/search/photo', { method: 'POST', body: fd })
  },
  agentSearch: (message) => req('/api/agent/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  }),
  checkDuplicate: (item) => req('/api/agent/check-duplicate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category: item.category, color_name: item.color_name,
                          pattern: item.pattern, material: item.material }),
  }),
  remove: (id) => req(`/api/items/${id}`, { method: 'DELETE' }),
  accuracy: () => req('/api/stats/accuracy'),
}

// Same vocabularies as backend/app/taxonomy.py
export const TAXONOMY = {
  classes: ['top', 'sweater', 'jacket', 'vest', 'pants', 'shorts', 'skirt', 'dress', 'glasses', 'hat',
    'headband', 'scarf', 'glove', 'watch', 'belt', 'sock', 'tights', 'shoe', 'bag', 'umbrella'],
  class_to_group: {
    top: 'Tops', sweater: 'Tops', vest: 'Tops', jacket: 'Outerwear', pants: 'Bottoms', shorts: 'Bottoms',
    skirt: 'Bottoms', dress: 'Dresses', shoe: 'Shoes', bag: 'Bags', glasses: 'Accessories', hat: 'Accessories',
    headband: 'Accessories', scarf: 'Accessories', glove: 'Accessories', watch: 'Accessories',
    belt: 'Accessories', sock: 'Accessories', tights: 'Accessories', umbrella: 'Accessories',
  },
  groups: ['Tops', 'Bottoms', 'Dresses', 'Outerwear', 'Shoes', 'Bags', 'Accessories'],
  patterns: ['solid', 'striped', 'checked', 'floral', 'polka dot', 'animal print', 'graphic', 'printed',
    'denim', 'knit texture', 'colorblock', 'other'],
  seasons: ['spring', 'summer', 'autumn', 'winter'],
  styles: ['casual', 'elegant', 'formal', 'business', 'sporty', 'streetwear', 'bohemian', 'minimalist',
    'classic', 'romantic'],
  occasions: ['everyday', 'work', 'party', 'date night', 'wedding', 'ceremony', 'sport', 'travel', 'beach',
    'lounge', 'outdoor'],
  colorFamilies: ['neutral', 'earth', 'warm', 'cool', 'pastel', 'bright', 'metallic', 'multicolor'],
}

export const COLORS = {
  black: '#1c1c1c', charcoal: '#3d3d3d', grey: '#8a8a8a', 'light grey': '#c8c8c8', white: '#f5f5f2',
  cream: '#efe6d2', beige: '#d6bf98', camel: '#b58a57', tan: '#c9a27a', brown: '#7a4a2a',
  chocolate: '#4a2c1d', khaki: '#b5a77a', olive: '#6b6b2f', green: '#3f8a4a', 'forest green': '#24452c',
  mint: '#a8dcc2', teal: '#1f7a7a', navy: '#1f2a4d', blue: '#3666b0', 'denim blue': '#4a6890',
  'light blue': '#9cc3e6', purple: '#6a3d8f', lavender: '#bfa8dc', burgundy: '#6e1f2e', red: '#c0282d',
  coral: '#ef7f6a', pink: '#e8a0b4', 'hot pink': '#d63c84', orange: '#e0772a', mustard: '#d1a12c',
  yellow: '#f0d43a', gold: '#c9a94b', silver: '#b8b8bc',
}

export function seasonLabel(seasons = []) {
  if (!seasons.length) return '—'
  if (seasons.length >= 4) return 'All seasons'
  const s = [...seasons].sort((a, b) => TAXONOMY.seasons.indexOf(a) - TAXONOMY.seasons.indexOf(b))
  const t = s.join('/')
  return t.charAt(0).toUpperCase() + t.slice(1)
}

export const cap = (s = '') => s.charAt(0).toUpperCase() + s.slice(1)
