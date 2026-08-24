import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { authApi } from '../api/auth'
import { ApiError } from '../api/client'
import { Field, Input } from '../components/Form'
import { Logo } from '../components/Logo'
import { useAuth } from '../features/auth/AuthContext'

function AuthFrame({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return <div className="auth-page"><section className="auth-story"><Logo/><div><span className="eyebrow">University scheduling, simplified</span><h1>One timetable. Clearer decisions. Fewer clashes.</h1><p>UniTime-AI brings students, faculty and timetable coordinators into one dependable scheduling workspace.</p></div><div className="auth-story__note">Built around your university's real timetable data and role-based workflows.</div></section><section className="auth-panel"><div className="auth-panel__inner"><h2>{title}</h2><p>{subtitle}</p>{children}</div></section></div>
}

export function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate(); const location = useLocation()
  const [email, setEmail] = useState(''); const [password, setPassword] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false)
  if (user) return <Navigate to="/dashboard" replace/>
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setError(''); try { await login(email, password); const from = (location.state as { from?: string } | null)?.from; navigate(from || '/dashboard', { replace: true }) } catch (err) { setError(err instanceof ApiError ? err.message : 'Unable to sign in.') } finally { setBusy(false) } }
  return <AuthFrame title="Welcome back" subtitle="Sign in with your UniTime-AI account."><form className="form-stack" onSubmit={submit}><Field label="Email"><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email"/></Field><Field label="Password"><Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password"/></Field>{error && <div className="form-error">{error}</div>}<button className="btn btn--primary btn--wide" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button></form><p className="auth-switch">New student? <Link to="/register">Create your account</Link></p></AuthFrame>
}

export function RegisterPage() {
  const { user } = useAuth(); const navigate = useNavigate()
  const [fullName, setFullName] = useState(''); const [email, setEmail] = useState(''); const [password, setPassword] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false)
  if (user) return <Navigate to="/dashboard" replace/>
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setError(''); try { await authApi.register(fullName, email, password); navigate('/login', { state: { registered: true } }) } catch (err) { setError(err instanceof ApiError ? err.message : 'Unable to create account.') } finally { setBusy(false) } }
  return <AuthFrame title="Student registration" subtitle="Create a student account. Faculty and privileged accounts are provisioned by the university."><form className="form-stack" onSubmit={submit}><Field label="Full name"><Input value={fullName} onChange={(e) => setFullName(e.target.value)} minLength={2} maxLength={200} required/></Field><Field label="University email"><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required/></Field><Field label="Password" hint="Use at least 8 characters."><Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} minLength={8} maxLength={128} required/></Field>{error && <div className="form-error">{error}</div>}<button className="btn btn--primary btn--wide" disabled={busy}>{busy ? 'Creating account…' : 'Create student account'}</button></form><p className="auth-switch">Already registered? <Link to="/login">Sign in</Link></p></AuthFrame>
}

export function ForbiddenPage() { return <div className="center-page"><div className="permission-card"><span>403</span><h1>That area isn't available for your role.</h1><p>Your account is signed in, but the requested action belongs to a different UniTime-AI role.</p><Link className="btn btn--primary" to="/dashboard">Return to dashboard</Link></div></div> }
