import { supabase } from '../supabase'

const I = {
  grid:   <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
  closet: <><rect x="4" y="3" width="16" height="18" rx="1.5" /><path d="M12 3v18M9.5 11v2M14.5 11v2" /></>,
  cube:   <><path d="M12 2 3 7v10l9 5 9-5V7z" /><path d="M3 7l9 5 9-5M12 12v10" /></>,
  bag:    <><path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 0 1-8 0"/></>,
}

const Icon = ({ name }) => (
  <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.6"
    strokeLinecap="round" strokeLinejoin="round">{I[name]}</svg>
)

const NAV = [
  { section: 'Wardrobe' },
  { id: 'wardrobe',  label: 'My Wardrobe',         icon: 'closet' },
  { id: '3d',        label: '3D Wardrobe',          icon: 'cube'   },
  { id: 'dashboard', label: 'Dashboard',            icon: 'grid'   },
  { section: 'Shopping' },
  { id: 'shopping',  label: 'Fashion Assistant',    icon: 'bag'    },
]

export default function Sidebar({ view, setView, user }) {
  const email = user?.email || ''
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="logo">Dress <span>Me</span></div>
        <div className="tagline">AI Style Intelligence</div>
      </div>
      <nav>
        {NAV.map((n, i) =>
          n.section ? (
            <div key={i} className="nav-section">{n.section}</div>
          ) : (
            <button key={n.id} className={`nav-item ${view === n.id ? 'active' : ''}`} onClick={() => setView(n.id)}>
              <Icon name={n.icon} />
              <span>{n.label}</span>
            </button>
          ),
        )}
      </nav>
      <div className="profile">
        <div className="avatar">{(email[0] || 'M').toUpperCase()}</div>
        <div className="pinfo">
          <div className="pname" title={email}>{email || 'My wardrobe'}</div>
          {supabase
            ? <button className="link psub" onClick={() => supabase.auth.signOut()}>Sign out</button>
            : <div className="psub">Local mode</div>}
        </div>
      </div>
    </aside>
  )
}
