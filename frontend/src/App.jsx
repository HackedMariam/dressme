import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { api, API } from './api'
import { supabase } from './supabase'
import Login from './components/Login'
import Sidebar from './components/Sidebar'
import WardrobeView from './components/WardrobeView'
import ItemPanel from './components/ItemPanel'
import Dashboard from './components/Dashboard'

const Wardrobe3D = lazy(() => import('./components/Wardrobe3D')) // three.js only loads when needed

export default function App() {
  const [session, setSession] = useState(undefined) // undefined = loading, null = signed out
  const [view, setView] = useState('wardrobe')
  const [items, setItems] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!supabase) { setSession(null); return }
    supabase.auth.getSession().then(({ data }) => setSession(data.session))
    const { data } = supabase.auth.onAuthStateChange((_e, s) => setSession(s))
    return () => data.subscription.unsubscribe()
  }, [])

  const signedIn = !supabase || !!session
  const userId = session?.user?.id

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const h = await api.health()
      setHealth(h)
      if (h.auth && !supabase) {
        throw new Error('The server requires sign-in but VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY are not set in frontend/.env.')
      }
      setItems(await api.list())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (signedIn) load()
    else { setItems([]); setSelectedId(null) }
  }, [signedIn, userId, load])

  if (session === undefined) return <div className="center muted">Loading…</div>
  if (!signedIn) return <Login />

  const selected = items.find((i) => i.id === selectedId) || null

  const upsert = (item) =>
    setItems((prev) => {
      const idx = prev.findIndex((i) => i.id === item.id)
      if (idx === -1) return [item, ...prev]
      const copy = [...prev]
      copy[idx] = item
      return copy
    })

  const onAdded = (newItems) => {
    newItems.forEach(upsert)
    if (newItems[0]) setSelectedId(newItems[0].id)
  }

  const onSave = async (id, fields, confirm = true) => upsert(await api.update(id, fields, confirm))
  const onReclassify = async (id) => upsert(await api.reclassify(id))
  const onDelete = async (id) => {
    await api.remove(id)
    setItems((prev) => prev.filter((i) => i.id !== id))
    setSelectedId(null)
  }

  return (
    <div className={`app ${selected ? 'with-panel' : ''}`}>
      <Sidebar view={view} setView={setView} user={session?.user} />
      <main className="main">
        {error ? (
          <div className="fatal">
            <h1>Can't load your wardrobe</h1>
            <p className="sub">{error}</p>
            <p className="muted">API: <code>{API}</code></p>
            <button className="btn primary" onClick={load}>Try again</button>
          </div>
        ) : loading && !items.length ? (
          <div className="center muted">Loading your wardrobe…</div>
        ) : (
          <>
            {health && !health.model_loaded && (
              <div className="banner">The detection model isn't loaded on the server, so new photos can't be analysed right now.</div>
            )}
            {view === 'wardrobe' && (
              <WardrobeView items={items} health={health} selectedId={selectedId}
                onSelect={setSelectedId} onAdded={onAdded} />
            )}
            {view === '3d' && (
              <Suspense fallback={<div className="center muted">Loading 3D wardrobe…</div>}>
                <Wardrobe3D items={items} selectedId={selectedId} onSelect={setSelectedId} />
              </Suspense>
            )}
            {view === 'dashboard' && <Dashboard items={items} health={health} />}
          </>
        )}
      </main>
      {selected && (
        <ItemPanel key={selected.id + JSON.stringify(selected.predicted || {})} item={selected} health={health}
          onClose={() => setSelectedId(null)} onSave={onSave} onReclassify={onReclassify} onDelete={onDelete} />
      )}
    </div>
  )
}
