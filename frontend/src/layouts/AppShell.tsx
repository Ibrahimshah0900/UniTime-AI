import { Bell, LogOut, Menu, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { notificationsApi } from '../api/notifications'
import { Logo } from '../components/Logo'
import { mobileStudentNav, navForRole } from '../app/navigation'
import { useAuth } from '../features/auth/AuthContext'
import { formatRelative, roleLabel } from '../utils/format'
import type { NotificationItem } from '../types/api'

export function AppShell() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [notices, setNotices] = useState<NotificationItem[]>([])
  const [unread, setUnread] = useState(0)
  const [noticeOpen, setNoticeOpen] = useState(false)

  useEffect(() => {
    if (!user) return
    notificationsApi.list({ limit: 5 }).then((data) => { setNotices(data.notifications); setUnread(data.unread_count) }).catch(() => undefined)
  }, [user])

  if (!user) return null
  const nav = navForRole(user.role)
  const shellClass = `app-shell app-shell--${user.role} ${collapsed ? 'app-shell--collapsed' : ''}`

  function signOut() { logout(); navigate('/login') }

  return <div className={shellClass}>
    <aside className={`sidebar ${mobileOpen ? 'sidebar--mobile-open' : ''}`}>
      <div className="sidebar__top"><Logo compact={collapsed}/><button className="icon-btn sidebar__collapse" onClick={() => setCollapsed((value) => !value)} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>{collapsed ? <PanelLeftOpen size={18}/> : <PanelLeftClose size={18}/>}</button></div>
      <nav className="sidebar__nav" aria-label="Primary navigation">{nav.map(({ label, path, icon: Icon }) => <NavLink key={path} to={path} onClick={() => setMobileOpen(false)} className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`}><Icon size={18}/>{!collapsed && <span>{label}</span>}</NavLink>)}</nav>
      <div className="sidebar__profile"><div className="avatar">{user.full_name.slice(0, 1).toUpperCase()}</div>{!collapsed && <div><strong>{user.full_name}</strong><span>{roleLabel(user.role)}</span></div>}<button className="icon-btn" onClick={signOut} aria-label="Log out"><LogOut size={17}/></button></div>
    </aside>

    <header className="topbar"><button className="icon-btn topbar__menu" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu/></button><div className="topbar__spacer"/><div className="notification-wrap"><button className="icon-btn notification-button" onClick={() => setNoticeOpen((value) => !value)} aria-label="Notifications"><Bell size={19}/>{unread > 0 && <span>{Math.min(unread, 9)}</span>}</button>{noticeOpen && <div className="notification-popover"><div className="notification-popover__header"><strong>Notifications</strong><button onClick={() => { setNoticeOpen(false); navigate('/notifications') }}>View all</button></div>{notices.length ? notices.map((notice) => <button className={`notification-mini ${notice.read_at ? '' : 'notification-mini--unread'}`} key={notice.id} onClick={() => { setNoticeOpen(false); navigate('/notifications') }}><strong>{notice.title}</strong><span>{notice.message}</span><small>{formatRelative(notice.created_at)}</small></button>) : <p className="muted">You're all caught up.</p>}</div>}</div><div className="topbar__identity"><div className="avatar">{user.full_name.slice(0, 1).toUpperCase()}</div><div><strong>{user.full_name}</strong><span>{roleLabel(user.role)}</span></div></div></header>

    <main className="app-main"><Outlet/></main>
    {user.role === 'student' && <nav className="mobile-bottom-nav">{mobileStudentNav.map(({ label, path, icon: Icon }) => <NavLink key={path} to={path} className={({ isActive }) => isActive ? 'active' : ''}><Icon size={19}/><span>{label}</span></NavLink>)}</nav>}
    {mobileOpen && <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setMobileOpen(false)}/>}
  </div>
}
