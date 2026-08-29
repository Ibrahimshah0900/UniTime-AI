import { Bell, LogOut, Menu, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { notificationsApi } from '../api/notifications'
import { mobileStudentNav, navForRole } from '../app/navigation'
import { Logo } from '../components/Logo'
import { useAuth } from '../features/auth/AuthContext'
import type { NotificationItem } from '../types/api'
import { formatRelative, roleLabel } from '../utils/format'

export function AppShell() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [notices, setNotices] = useState<NotificationItem[]>([])
  const [unread, setUnread] = useState(0)
  const [noticeOpen, setNoticeOpen] = useState(false)

  useEffect(() => {
    if (!user) return

    const refreshNotifications = () => {
      notificationsApi.list({ limit: 5 })
        .then((data) => {
          setNotices(data.notifications)
          setUnread(data.unread_count)
        })
        .catch(() => undefined)
    }

    refreshNotifications()
    window.addEventListener('unitime:notifications-changed', refreshNotifications)
    return () => window.removeEventListener('unitime:notifications-changed', refreshNotifications)
  }, [user])

  if (!user) return null

  const nav = navForRole(user.role)
  const currentNavItem = [...nav]
    .sort((first, second) => second.path.length - first.path.length)
    .find(({ path }) => location.pathname === path || location.pathname.startsWith(`${path}/`))

  const shellClass = `app-shell app-shell--${user.role} ${collapsed ? 'app-shell--collapsed' : ''}`

  function signOut() {
    logout()
    navigate('/login')
  }

  return <div className={shellClass}>
    <aside id="primary-navigation" className={`sidebar ${mobileOpen ? 'sidebar--mobile-open' : ''}`}>
      <div className="sidebar__top">
        <Logo compact={collapsed}/>
        <button
          className="icon-btn sidebar__collapse"
          onClick={() => setCollapsed((value) => !value)}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <PanelLeftOpen size={18}/> : <PanelLeftClose size={18}/>}
        </button>
      </div>

      <nav className="sidebar__nav" aria-label="Primary navigation">
        {nav.map(({ label, path, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            onClick={() => setMobileOpen(false)}
            className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`}
          >
            <Icon size={18}/>
            {!collapsed && <span>{label}</span>}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar__profile">
        <div className="avatar">{user.full_name.slice(0, 1).toUpperCase()}</div>
        {!collapsed && <div>
          <strong>{user.full_name}</strong>
          <span>{roleLabel(user.role)}</span>
        </div>}
        <button className="icon-btn" onClick={signOut} aria-label="Log out">
          <LogOut size={17}/>
        </button>
      </div>
    </aside>

    <header className="topbar">
      <button
        className="icon-btn topbar__menu"
        onClick={() => setMobileOpen(true)}
        aria-label="Open navigation"
        aria-controls="primary-navigation"
        aria-expanded={mobileOpen}
      >
        <Menu/>
      </button>

      <div className="topbar__context">
        <span>{roleLabel(user.role)} workspace</span>
        <strong>{currentNavItem?.label || 'UniTime-AI'}</strong>
      </div>

      <div className="topbar__spacer"/>

      <div className="notification-wrap">
        <button
          className="icon-btn notification-button"
          onClick={() => setNoticeOpen((value) => !value)}
          aria-label="Notifications"
          aria-expanded={noticeOpen}
          aria-haspopup="dialog"
        >
          <Bell size={19}/>
          {unread > 0 && <span>{Math.min(unread, 9)}</span>}
        </button>

        <AnimatePresence>
          {noticeOpen && (
            <motion.div
              key="notification-popover"
              className="notification-popover"
              role="dialog"
              aria-label="Recent notifications"
              initial={{ opacity: 0, y: -7, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -5, scale: 0.985 }}
              transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            >
              <div className="notification-popover__header">
                <strong>Notifications</strong>
                <button onClick={() => {
                  setNoticeOpen(false)
                  navigate('/notifications')
                }}>
                  View all
                </button>
              </div>

              {notices.length
                ? notices.map((notice) => (
                    <button
                      className={`notification-mini ${notice.read_at ? '' : 'notification-mini--unread'}`}
                      key={notice.id}
                      onClick={() => {
                        setNoticeOpen(false)
                        navigate('/notifications')
                      }}
                    >
                      <strong>{notice.title}</strong>
                      <span>{notice.message}</span>
                      <small>{formatRelative(notice.created_at)}</small>
                    </button>
                  ))
                : <p className="muted">You're all caught up.</p>}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div className="topbar__identity">
        <div className="avatar">{user.full_name.slice(0, 1).toUpperCase()}</div>
        <div>
          <strong>{user.full_name}</strong>
          <span>{roleLabel(user.role)}</span>
        </div>
      </div>
    </header>

    <main className="app-main">
      <Outlet/>
    </main>

    {user.role === 'student' && (
      <nav className="mobile-bottom-nav" aria-label="Student navigation">
        {mobileStudentNav.map(({ label, path, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) => isActive ? 'active' : ''}
          >
            <Icon size={19}/>
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
    )}

    {mobileOpen && (
      <button
        className="mobile-scrim"
        aria-label="Close navigation"
        onClick={() => setMobileOpen(false)}
      />
    )}
  </div>
}
