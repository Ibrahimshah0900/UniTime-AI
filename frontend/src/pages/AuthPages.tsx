import { motion } from 'motion/react'
import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { authApi } from '../api/auth'
import { ApiError } from '../api/client'
import { Field, Input } from '../components/Form'
import { Logo } from '../components/Logo'
import { useAuth } from '../features/auth/AuthContext'

function AuthFrame({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return <div className="auth-page">
    <motion.section className="auth-story" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.35 }}>
      <Logo/>
      <div className="auth-story__content">
        <span className="eyebrow">University scheduling intelligence</span>
        <h1>One timetable.<br/>Clearer decisions.<br/>Fewer clashes.</h1>
        <p>UniTime-AI brings students, faculty and timetable coordinators into one dependable scheduling workspace.</p>
        <div className="auth-story__features" aria-label="Platform capabilities">
          <span>Conflict-aware</span>
          <span>Role-aware</span>
          <span>Term-aware</span>
        </div>
      </div>
      <div className="auth-story__note">
        <strong>Scheduling you can trust.</strong>
        <span>Built around institutional timetable data and controlled workflows.</span>
      </div>
    </motion.section>

    <motion.section
      className="auth-panel"
      initial={{ opacity: 0, x: 16 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.34, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="auth-panel__inner">
        <span className="auth-panel__eyebrow">UniTime-AI</span>
        <h2>{title}</h2>
        <p>{subtitle}</p>
        {children}
      </div>
    </motion.section>
  </div>
}

export function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate(); const location = useLocation()
  const [identifier, setIdentifier] = useState(''); const [password, setPassword] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false)
  if (user) return <Navigate to="/dashboard" replace/>
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setError(''); try { const authenticated = await login(identifier, password); const from = (location.state as { from?: string } | null)?.from; const firstLogin = Boolean(authenticated.must_change_password || (authenticated.role === 'student' && authenticated.student_profile && !authenticated.student_profile.onboarding_completed)); navigate(firstLogin ? '/account' : from || '/dashboard', { replace: true }) } catch (err) { setError(err instanceof ApiError ? err.message : 'Unable to sign in.') } finally { setBusy(false) } }
  return <AuthFrame title="Welcome back" subtitle="Sign in with your email or student registration number."><form className="form-stack" onSubmit={submit}><Field label="Email or registration number"><Input value={identifier} onChange={(e) => setIdentifier(e.target.value)} required autoComplete="username" autoCapitalize="none"/></Field><Field label="Password"><Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password"/></Field>{error && <div className="form-error">{error}</div>}<button className="btn btn--primary btn--wide" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button></form><p className="auth-switch">New student? <Link to="/register">Create your account</Link></p></AuthFrame>
}

export function RegisterPage() {
  const { user } = useAuth(); const navigate = useNavigate()
  const [fullName, setFullName] = useState(''); const [email, setEmail] = useState(''); const [password, setPassword] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false)
  if (user) return <Navigate to="/dashboard" replace/>
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setError(''); try { await authApi.register(fullName, email, password); navigate('/login', { state: { registered: true } }) } catch (err) { setError(err instanceof ApiError ? err.message : 'Unable to create account.') } finally { setBusy(false) } }
  return <AuthFrame title="Student registration" subtitle="Create a student account. Faculty and privileged accounts are provisioned by the university."><form className="form-stack" onSubmit={submit}><Field label="Full name"><Input value={fullName} onChange={(e) => setFullName(e.target.value)} minLength={2} maxLength={200} required/></Field><Field label="University email"><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required/></Field><Field label="Password" hint="Use at least 8 characters."><Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} minLength={8} maxLength={128} required/></Field>{error && <div className="form-error">{error}</div>}<button className="btn btn--primary btn--wide" disabled={busy}>{busy ? 'Creating account…' : 'Create student account'}</button></form><p className="auth-switch">Already registered? <Link to="/login">Sign in</Link></p></AuthFrame>
}

export function ForbiddenPage() { return <div className="center-page"><div className="permission-card"><span>403</span><h1>That area isn't available for your role.</h1><p>Your account is signed in, but the requested action belongs to a different UniTime-AI role.</p><Link className="btn btn--primary" to="/dashboard">Return to dashboard</Link></div></div> }
