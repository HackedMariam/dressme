import { useState } from 'react'
import { supabase } from '../supabase'

export default function Login() {
  const [mode, setMode] = useState('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError(''); setInfo('')
    try {
      if (mode === 'signin') {
        const { error } = await supabase.auth.signInWithPassword({ email, password })
        if (error) throw error
      } else if (mode === 'signup') {
        const { data, error } = await supabase.auth.signUp({ email, password })
        if (error) throw error
        if (!data.session) setInfo('Check your inbox to confirm your email, then sign in.')
      } else {
        const { error } = await supabase.auth.resetPasswordForEmail(email, { redirectTo: window.location.origin })
        if (error) throw error
        setInfo('If an account exists for this email, a reset link is on its way.')
      }
    } catch (err) {
      setError(err.message || 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  const title = { signin: 'Welcome back', signup: 'Create your wardrobe', reset: 'Reset password' }[mode]

  return (
    <div className="auth">
      <div className="auth-side">
        <div className="logo">Dress <span>Me</span></div>
        <div className="tagline">AI Style Intelligence</div>
        <p>Photograph your clothes. We detect each item, read its colour, and classify it by occasion,
          style and season — then hang it in your 3D wardrobe.</p>
      </div>
      <form className="auth-card" onSubmit={submit}>
        <h1>{title}</h1>
        <label>Email
          <input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        {mode !== 'reset' && (
          <label>Password
            <input type="password" required minLength={8} value={password}
              autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
              onChange={(e) => setPassword(e.target.value)} />
          </label>
        )}
        {error && <p className="err">{error}</p>}
        {info && <p className="ok">{info}</p>}
        <button className="btn primary" disabled={busy}>
          {busy ? 'Please wait…' : mode === 'signin' ? 'Sign in' : mode === 'signup' ? 'Create account' : 'Send reset link'}
        </button>
        <div className="auth-links">
          {mode !== 'signin' && <button type="button" className="link" onClick={() => setMode('signin')}>Sign in</button>}
          {mode !== 'signup' && <button type="button" className="link" onClick={() => setMode('signup')}>Create an account</button>}
          {mode === 'signin' && <button type="button" className="link" onClick={() => setMode('reset')}>Forgot password?</button>}
        </div>
      </form>
    </div>
  )
}
