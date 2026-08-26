import { BarChart3, ShieldAlert } from 'lucide-react'
import { insightsApi } from '../api/insights'
import { EmptyState, ErrorState, LoadingState, Metric, PageHeader, Section, StatusBadge } from '../components/Ui'
import { useAsync } from '../hooks/useAsync'
import { formatRelative, titleCase } from '../utils/format'

function severityTone(severity: string) {
  if (severity === 'critical' || severity === 'error') return 'danger'
  if (severity === 'warning') return 'warning'
  if (severity === 'info') return 'info'
  return 'neutral'
}

function rateLabel(value: number | null) {
  return value === null ? 'Unavailable' : `${value}%`
}

export function InsightsPage() {
  const quality = useAsync(() => insightsApi.dataQuality(), [])
  const analytics = useAsync(() => insightsApi.resolverAnalytics(), [])

  return <div className="page">
    <PageHeader title="Resolver quality & analytics" description="Read-only operational diagnostics and measured clash-resolution outcomes for the current academic term." />

    <Section title="Resolver analytics" description="Live conflict state plus persisted resolution outcomes. Unavailable metrics are never estimated." actions={<BarChart3 size={18}/> }>
      {analytics.loading ? <LoadingState label="Loading resolver analytics"/> : analytics.error ? <ErrorState message={analytics.error} retry={analytics.reload}/> : analytics.data ? <>
        <div className="metric-grid">
          <Metric label="Confirmed conflicts" value={analytics.data.current_confirmed_conflicts} tone={analytics.data.current_confirmed_conflicts ? 'warning' : 'success'} />
          <Metric label="Structural clashes" value={analytics.data.current_structural_clashes} tone={analytics.data.current_structural_clashes ? 'danger' : 'success'} />
          <Metric label="Verified students" value={analytics.data.current_verified_students} />
          <Metric label="Reports" value={analytics.data.report_total} />
          <Metric label="Applied resolutions" value={analytics.data.resolution_applications} tone="success" />
          <Metric label="Undo rate" value={rateLabel(analytics.data.undo_rate.value)} hint={analytics.data.undo_rate.reason || undefined} />
          <Metric label="Shared resolutions" value={rateLabel(analytics.data.shared_resolution_percentage)} />
          <Metric label="Avg. first resolution" value={analytics.data.average_first_resolution_hours === null ? '—' : `${analytics.data.average_first_resolution_hours}h`} />
        </div>
        <div className="insight-note"><strong>Recommendation acceptance</strong><span>{rateLabel(analytics.data.recommendation_acceptance_rate.value)}</span><p>{analytics.data.recommendation_acceptance_rate.reason || 'Measured from persisted recommendation events.'}</p></div>
        <p className="muted">Updated {formatRelative(analytics.data.generated_at)} · Term {analytics.data.term_code}</p>
      </> : null}
    </Section>

    <Section title="Data-quality diagnostics" description="Actionable read-only findings. Nothing on this page repairs or deletes institutional data automatically." actions={<ShieldAlert size={18}/> }>
      {quality.loading ? <LoadingState label="Running data-quality checks"/> : quality.error ? <ErrorState message={quality.error} retry={quality.reload}/> : quality.data ? <>
        <div className="metric-grid">
          <Metric label="Total findings" value={quality.data.summary.total} />
          <Metric label="Critical" value={quality.data.summary.critical} tone={quality.data.summary.critical ? 'danger' : 'success'} />
          <Metric label="Errors" value={quality.data.summary.error} tone={quality.data.summary.error ? 'danger' : 'success'} />
          <Metric label="Warnings" value={quality.data.summary.warning} tone={quality.data.summary.warning ? 'warning' : 'success'} />
        </div>
        {quality.data.issues.length ? <div className="quality-list">{quality.data.issues.map((issue, index) => <article key={`${issue.issue_code}-${issue.entity_id || 'group'}-${index}`} className="quality-item">
          <div className="quality-item__heading"><strong>{titleCase(issue.issue_code)}</strong><StatusBadge tone={severityTone(issue.severity)}>{titleCase(issue.severity)}</StatusBadge></div>
          <p>{issue.message}</p>
          <small>{titleCase(issue.entity_type)}{issue.entity_id ? ` #${issue.entity_id}` : ''} · {titleCase(issue.scope)} scope</small>
          <div className="quality-item__suggestion"><strong>Suggested correction</strong><span>{issue.suggested_correction}</span></div>
        </article>)}</div> : <EmptyState title="No data-quality findings" description="The configured checks found no issues for this term and global institutional identities."/>}
        <p className="muted">{quality.data.important_note}</p>
      </> : null}
    </Section>
  </div>
}
