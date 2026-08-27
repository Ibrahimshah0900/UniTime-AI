import { ArrowRight, Bell, CalendarDays, ClipboardList, ShieldCheck, TriangleAlert, type LucideIcon } from 'lucide-react'
import { motion } from 'motion/react'
import { Link } from 'react-router-dom'
import { dashboardApi } from '../api/dashboards'
import { facultyApi } from '../api/faculty'
import { notificationsApi } from '../api/notifications'
import { reportsApi } from '../api/reports'
import { studentApi } from '../api/student'
import { ErrorState, LoadingState, Metric, PageHeader, Section, StatusBadge } from '../components/Ui'
import { useAuth } from '../features/auth/AuthContext'
import { useAsync } from '../hooks/useAsync'
import type { UserRole } from '../types/api'
import { classLabel, dashboardMetricEntries, formatClock, statusTone, titleCase } from '../utils/format'
import { nextClass } from '../utils/timetable'

type HeroConfig = {
  kicker: string
  title: string
  description: string
  href: string
  action: string
  icon: LucideIcon
}

export function DashboardPage() {
  const { user } = useAuth()
  const dashboard = useAsync(() => dashboardApi.get(), [])
  const schedule = useAsync(
    async () => user?.role === 'student'
      ? studentApi.timetable()
      : user?.role === 'faculty'
        ? facultyApi.timetable()
        : [],
    [user?.role],
  )
  const notices = useAsync(() => notificationsApi.list({ limit: 4 }), [])
  const reports = useAsync(
    async () => user?.role === 'student'
      ? studentApi.clashReports(0, 4)
      : user && ['coordinator', 'admin'].includes(user.role)
        ? reportsApi.queue('', 0, 4)
        : null,
    [user?.role],
  )

  if (!user) return null
  if (dashboard.loading) return <LoadingState label="Preparing your dashboard"/>
  if (dashboard.error || !dashboard.data) {
    return <ErrorState message={dashboard.error || 'Dashboard unavailable'} retry={dashboard.reload}/>
  }

  const metrics = dashboardMetricEntries(dashboard.data.data)
  const upcoming = nextClass(schedule.data || [])
  const hero = heroForRole(user.role)
  const HeroIcon = hero.icon

  return <div className="page dashboard-page">
    <PageHeader
      title={`Good ${greeting()}, ${user.full_name.split(' ')[0]}`}
      description={dashboard.data.generated_for_day
        ? `Your ${titleCase(user.role)} workspace for ${dashboard.data.generated_for_day}.`
        : 'Here is what needs your attention.'}
      actions={dashboard.data.generated_for_day
        ? <span className="dashboard-date-pill">{dashboard.data.generated_for_day}</span>
        : undefined}
    />

    <motion.section
      className="dashboard-hero"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.34, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="dashboard-hero__copy">
        <span className="eyebrow">{hero.kicker}</span>
        <h2>{hero.title}</h2>
        <p>{hero.description}</p>

        <div className="dashboard-hero__actions">
          <Link className="btn btn--primary dashboard-hero__cta" to={hero.href}>
            {hero.action}
            <ArrowRight size={15}/>
          </Link>

          <span className="dashboard-hero__signal">
            <span className="dashboard-hero__signal-dot"/>
            Role-aware workspace
          </span>
        </div>
      </div>

      <div className="dashboard-hero__visual" aria-hidden="true">
        <div className="dashboard-hero__halo"/>
        <div className="dashboard-hero__icon">
          <HeroIcon size={36}/>
        </div>

        <span className="dashboard-hero__tag dashboard-hero__tag--one">
          Schedule
        </span>
        <span className="dashboard-hero__tag dashboard-hero__tag--two">
          Updates
        </span>
        <span className="dashboard-hero__tag dashboard-hero__tag--three">
          Actions
        </span>
      </div>
    </motion.section>

    <div className="metric-grid dashboard-metrics">
      {metrics.length
        ? metrics.map(([key, value], index) => (
            <Metric
              key={key}
              label={titleCase(key)}
              value={String(value)}
              tone={['success', 'info', 'warning', 'neutral'][index % 4]}
            />
          ))
        : <Metric
            label="Role"
            value={titleCase(user.role)}
            hint="Operational dashboard"
            tone="success"
          />}
    </div>

    {(user.role === 'student' || user.role === 'faculty') && (
      <div className="dashboard-columns dashboard-columns--personal">
        <Section
          title={user.role === 'student' ? 'Your day' : 'Teaching today'}
          description="Live from your personal schedule."
          className="dashboard-panel dashboard-panel--schedule"
        >
          {schedule.loading
            ? <LoadingState label="Loading your schedule"/>
            : schedule.error
              ? <ErrorState message={schedule.error} retry={schedule.reload}/>
              : upcoming
                ? <div className="next-class next-class--dashboard">
                    <div className="next-class__top">
                      <span>Next class</span>
                      <span className="next-class__time">
                        {formatClock(upcoming.start_time)} - {formatClock(upcoming.end_time)}
                      </span>
                    </div>

                    <strong>{classLabel(upcoming)}</strong>

                    <p>
                      {upcoming.course_code || 'Scheduled class'}
                      {upcoming.section ? ` / Section ${upcoming.section}` : ''}
                    </p>

                    <div className="next-class__footer">
                      <span>{upcoming.room || 'Room TBA'}</span>
                      <Link to="/timetable">
                        Open timetable
                        <ArrowRight size={14}/>
                      </Link>
                    </div>
                  </div>
                : <div className="soft-panel dashboard-empty">
                    No upcoming class was found in your current timetable.
                  </div>}
        </Section>

        <Section
          title="Recent notifications"
          actions={<Link className="text-link" to="/notifications">View all</Link>}
          className="dashboard-panel"
        >
          {notices.loading
            ? <LoadingState label="Loading notifications"/>
            : notices.error
              ? <ErrorState message={notices.error} retry={notices.reload}/>
              : notices.data?.notifications.length
                ? <div className="feed feed--dashboard">
                    {notices.data.notifications.map((item) => (
                      <article className="feed__item dashboard-notice" key={item.id}>
                        <div className="dashboard-notice__icon">
                          <Bell size={15}/>
                        </div>

                        <div>
                          <strong>{item.title}</strong>
                          <span>{item.message}</span>
                        </div>
                      </article>
                    ))}
                  </div>
                : <div className="soft-panel dashboard-empty">
                    No recent notifications.
                  </div>}
        </Section>
      </div>
    )}

    {user.role === 'student' && (
      <Section
        title="Active clash reports"
        actions={<Link className="text-link" to="/clash-reports">Open reports</Link>}
        className="dashboard-followup"
      >
        {reports.loading
          ? <LoadingState label="Loading clash reports"/>
          : reports.error
            ? <ErrorState message={reports.error} retry={reports.reload}/>
            : reports.data && reports.data.reports.length
              ? <div className="report-strip report-strip--dashboard">
                  {reports.data.reports.map((report) => (
                    <article key={report.id}>
                      <div>
                        <strong>Report #{report.id}</strong>
                        <span>{report.items.map((item) => item.course_code).join(' / ')}</span>
                      </div>

                      <StatusBadge tone={statusTone(report.status)}>
                        {titleCase(report.status)}
                      </StatusBadge>
                    </article>
                  ))}
                </div>
              : <div className="soft-panel dashboard-empty">
                  No clash reports are currently attached to your account.
                </div>}
      </Section>
    )}

    {['coordinator', 'admin'].includes(user.role) && (
      <div className="dashboard-columns dashboard-columns--ops">
        <Section
          title="Operations"
          description="Fast access to the workspaces used to keep the timetable healthy."
          className="dashboard-panel"
        >
          <div className="quick-grid quick-grid--dashboard">
            <Link className="dashboard-quick-card" to="/timetable">
              <span className="dashboard-quick-card__icon">
                <CalendarDays size={18}/>
              </span>
              <span className="dashboard-quick-card__copy">
                <strong>Timetable</strong>
                <span>Manage entries and imports</span>
              </span>
              <ArrowRight className="dashboard-quick-card__arrow" size={15}/>
            </Link>

            <Link className="dashboard-quick-card" to="/clashes">
              <span className="dashboard-quick-card__icon">
                <TriangleAlert size={18}/>
              </span>
              <span className="dashboard-quick-card__copy">
                <strong>Clashes</strong>
                <span>Inspect structural and student risk</span>
              </span>
              <ArrowRight className="dashboard-quick-card__arrow" size={15}/>
            </Link>

            <Link className="dashboard-quick-card" to="/clash-reports">
              <span className="dashboard-quick-card__icon">
                <ClipboardList size={18}/>
              </span>
              <span className="dashboard-quick-card__copy">
                <strong>Student reports</strong>
                <span>Review submitted cases</span>
              </span>
              <ArrowRight className="dashboard-quick-card__arrow" size={15}/>
            </Link>

            <Link className="dashboard-quick-card" to="/optimizer">
              <span className="dashboard-quick-card__icon">
                <ShieldCheck size={18}/>
              </span>
              <span className="dashboard-quick-card__copy">
                <strong>Optimizer</strong>
                <span>Review and apply safe improvements</span>
              </span>
              <ArrowRight className="dashboard-quick-card__arrow" size={15}/>
            </Link>
          </div>
        </Section>

        <Section
          title="Student report queue"
          actions={<Link className="text-link" to="/clash-reports">Review queue</Link>}
          className="dashboard-panel"
        >
          {reports.loading
            ? <LoadingState label="Loading report queue"/>
            : reports.error
              ? <ErrorState message={reports.error} retry={reports.reload}/>
              : reports.data && reports.data.reports.length
                ? <div className="report-strip report-strip--dashboard">
                    {reports.data.reports.map((report) => (
                      <article key={report.id}>
                        <div>
                          <strong>#{report.id} / {report.student_name}</strong>
                          <span>{report.items.map((item) => item.course_code).join(' / ')}</span>
                        </div>

                        <StatusBadge tone={statusTone(report.status)}>
                          {titleCase(report.status)}
                        </StatusBadge>
                      </article>
                    ))}
                  </div>
                : <div className="soft-panel dashboard-empty">
                    No reports waiting in the current view.
                  </div>}
        </Section>
      </div>
    )}
  </div>
}

function heroForRole(role: UserRole): HeroConfig {
  if (role === 'student') {
    return {
      kicker: 'Student command center',
      title: 'Your week, without the noise.',
      description: 'See what is next, catch schedule updates, and keep timetable conflicts from becoming surprises.',
      href: '/timetable',
      action: 'View my schedule',
      icon: CalendarDays,
    }
  }

  if (role === 'faculty') {
    return {
      kicker: 'Faculty command center',
      title: 'Teaching, already organized.',
      description: 'Keep your assigned classes, timetable changes, and university updates in one focused workspace.',
      href: '/timetable',
      action: 'Open teaching timetable',
      icon: CalendarDays,
    }
  }

  if (role === 'coordinator') {
    return {
      kicker: 'Scheduling operations',
      title: 'Keep the timetable healthy.',
      description: 'Move from timetable signals to verified action with clashes, reports, and safe scheduling tools close at hand.',
      href: '/clashes',
      action: 'Review clashes',
      icon: TriangleAlert,
    }
  }

  return {
    kicker: 'Administration control',
    title: 'Access and operations, under control.',
    description: 'Manage the operational workspace while keeping university scheduling and account administration easy to inspect.',
    href: '/admin/users',
    action: 'Manage users and roles',
    icon: ShieldCheck,
  }
}

function greeting() {
  const hour = new Date().getHours()
  return hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening'
}
