import { ArrowRight, Bell, CalendarDays, ClipboardList, TriangleAlert } from 'lucide-react'
import { Link } from 'react-router-dom'
import { dashboardApi } from '../api/dashboards'
import { facultyApi } from '../api/faculty'
import { notificationsApi } from '../api/notifications'
import { reportsApi } from '../api/reports'
import { studentApi } from '../api/student'
import { ErrorState, LoadingState, Metric, PageHeader, Section, StatusBadge } from '../components/Ui'
import { useAuth } from '../features/auth/AuthContext'
import { useAsync } from '../hooks/useAsync'
import { classLabel, dashboardMetricEntries, formatClock, statusTone, titleCase } from '../utils/format'
import { nextClass } from '../utils/timetable'

export function DashboardPage() {
  const { user } = useAuth()
  const dashboard = useAsync(() => dashboardApi.get(), [])
  const schedule = useAsync(async () => user?.role === 'student' ? studentApi.timetable() : user?.role === 'faculty' ? facultyApi.timetable() : [], [user?.role])
  const notices = useAsync(() => notificationsApi.list({ limit: 4 }), [])
  const reports = useAsync(async () => user?.role === 'student' ? studentApi.clashReports(0, 4) : user && ['coordinator','admin'].includes(user.role) ? reportsApi.queue('', 0, 4) : null, [user?.role])
  if (!user) return null
  if (dashboard.loading) return <LoadingState label="Preparing your dashboard"/>
  if (dashboard.error || !dashboard.data) return <ErrorState message={dashboard.error || 'Dashboard unavailable'} retry={dashboard.reload}/>
  const metrics = dashboardMetricEntries(dashboard.data.data)
  const upcoming = nextClass(schedule.data || [])

  return <div className="page"><PageHeader title={`Good ${greeting()}, ${user.full_name.split(' ')[0]}`} description={dashboard.data.generated_for_day ? `Your ${titleCase(user.role)} workspace for ${dashboard.data.generated_for_day}.` : 'Here is what needs your attention.'}/>
    <div className="metric-grid">{metrics.length ? metrics.map(([key, value], index) => <Metric key={key} label={titleCase(key)} value={String(value)} tone={['success','info','warning','neutral'][index % 4]}/>) : <Metric label="Role" value={titleCase(user.role)} hint="Operational dashboard" tone="success"/>}</div>

    {(user.role === 'student' || user.role === 'faculty') && <div className="dashboard-columns"><Section title={user.role === 'student' ? 'Your day' : 'Teaching today'} description="Live from your personal schedule.">{schedule.loading ? <LoadingState label="Loading your schedule"/> : schedule.error ? <ErrorState message={schedule.error} retry={schedule.reload}/> : upcoming ? <div className="next-class"><span>Next class</span><strong>{classLabel(upcoming)}</strong><p>{formatClock(upcoming.start_time)} – {formatClock(upcoming.end_time)} · {upcoming.room || 'Room TBA'}</p><Link to="/timetable">Open timetable <ArrowRight size={15}/></Link></div> : <div className="soft-panel">No upcoming class was found in your current timetable.</div>}</Section><Section title="Recent notifications" actions={<Link className="text-link" to="/notifications">View all</Link>}>{notices.loading ? <LoadingState label="Loading notifications"/> : notices.error ? <ErrorState message={notices.error} retry={notices.reload}/> : notices.data?.notifications.length ? <div className="feed">{notices.data.notifications.map((item) => <div className="feed__item" key={item.id}><Bell size={16}/><div><strong>{item.title}</strong><span>{item.message}</span></div></div>)}</div> : <div className="soft-panel">No recent notifications.</div>}</Section></div>}

    {user.role === 'student' && <Section title="Active clash reports" actions={<Link className="text-link" to="/clash-reports">Open reports</Link>}>{reports.loading ? <LoadingState label="Loading clash reports"/> : reports.error ? <ErrorState message={reports.error} retry={reports.reload}/> : reports.data && reports.data.reports.length ? <div className="report-strip">{reports.data.reports.map((report) => <article key={report.id}><div><strong>Report #{report.id}</strong><span>{report.items.map((item) => item.course_code).join(' · ')}</span></div><StatusBadge tone={statusTone(report.status)}>{titleCase(report.status)}</StatusBadge></article>)}</div> : <div className="soft-panel">No clash reports are currently attached to your account.</div>}</Section>}

    {['coordinator','admin'].includes(user.role) && <div className="dashboard-columns dashboard-columns--ops"><Section title="Operations" description="Fast access to the workspaces used to keep the timetable healthy."><div className="quick-grid"><Link to="/timetable"><CalendarDays/><strong>Timetable</strong><span>Manage entries and imports</span></Link><Link to="/clashes"><TriangleAlert/><strong>Clashes</strong><span>Inspect structural and student risk</span></Link><Link to="/clash-reports"><ClipboardList/><strong>Student reports</strong><span>Review submitted cases</span></Link><Link to="/optimizer"><ArrowRight/><strong>Optimizer</strong><span>Review and apply safe improvements</span></Link></div></Section><Section title="Student report queue" actions={<Link className="text-link" to="/clash-reports">Review queue</Link>}>{reports.loading ? <LoadingState label="Loading report queue"/> : reports.error ? <ErrorState message={reports.error} retry={reports.reload}/> : reports.data && reports.data.reports.length ? <div className="report-strip">{reports.data.reports.map((report) => <article key={report.id}><div><strong>#{report.id} · {report.student_name}</strong><span>{report.items.map((item) => item.course_code).join(' · ')}</span></div><StatusBadge tone={statusTone(report.status)}>{titleCase(report.status)}</StatusBadge></article>)}</div> : <div className="soft-panel">No reports waiting in the current view.</div>}</Section></div>}
  </div>
}

function greeting() { const hour = new Date().getHours(); return hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening' }
