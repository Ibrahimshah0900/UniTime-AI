import { BarChart3, ShieldAlert } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { insightsApi } from '../api/insights'
import { termsApi } from '../api/terms'
import { Select } from '../components/Form'
import {
  EmptyState,
  ErrorNote,
  ErrorState,
  LoadingState,
  Metric,
  PageHeader,
  Section,
  StatusBadge,
} from '../components/Ui'
import { useAsync } from '../hooks/useAsync'
import { formatRelative, titleCase } from '../utils/format'

const schedulingIssueCodes = new Set([
  'OFFERING_WITHOUT_FACULTY_ALLOCATION',
  'AMBIGUOUS_OFFERING_FACULTY_ALLOCATION',
  'OFFERING_MISSING_ROOM',
  'MISSING_FACULTY_TEACHING_PROFILE',
  'FACULTY_MISSING_AVAILABILITY',
  'FACULTY_REQUIRED_DAY_AVAILABILITY_MISSING',
  'FACULTY_LOAD_EXCEEDS_DESIGNATION_LIMIT',
  'GENERATED_ENTRY_POLICY_MISMATCH',
  'GENERATED_ENTRY_WITHOUT_COURSE_OFFERING',
  'GENERATED_ENTRY_OFFERING_METADATA_MISMATCH',
])

function severityTone(severity: string) {
  if (severity === 'critical' || severity === 'error') return 'danger'
  if (severity === 'warning') return 'warning'
  if (severity === 'info') return 'info'
  return 'neutral'
}

function rateLabel(value: number | null) {
  return value === null ? 'Unavailable' : `${value}%`
}

function isSchedulingIssue(issueCode: string) {
  return schedulingIssueCodes.has(issueCode)
}

export function InsightsPage() {
  const terms = useAsync(() => termsApi.list(), [])
  const [selectedTermId, setSelectedTermId] = useState<number | null>(null)
  const effectiveTermId =
    selectedTermId ??
    terms.data?.active_term_id ??
    terms.data?.terms[0]?.id ??
    null
  const selectedTerm =
    terms.data?.terms.find((term) => term.id === effectiveTermId) ?? null

  const quality = useAsync(
    () =>
      terms.loading || !effectiveTermId
        ? Promise.resolve(null)
        : insightsApi.dataQuality(effectiveTermId),
    [terms.loading, effectiveTermId],
  )
  const analytics = useAsync(
    () =>
      terms.loading || !effectiveTermId
        ? Promise.resolve(null)
        : insightsApi.resolverAnalytics(effectiveTermId),
    [terms.loading, effectiveTermId],
  )

  const schedulingFindings =
    quality.data?.issues.filter((issue) => isSchedulingIssue(issue.issue_code))
      .length ?? 0

  return (
    <div className="page">
      <PageHeader
        title="Resolver quality & analytics"
        description="Read-only operational diagnostics and measured clash-resolution outcomes for the selected academic term."
        actions={
          selectedTerm?.status === 'planning' ? (
            <Link className="btn btn--secondary" to="/scheduling">
              Open scheduling
            </Link>
          ) : undefined
        }
      />

      {terms.error && <ErrorNote>{terms.error}</ErrorNote>}

      <div className="toolbar">
        <Select
          aria-label="Academic term"
          value={effectiveTermId ? String(effectiveTermId) : ''}
          onChange={(event) => setSelectedTermId(Number(event.target.value))}
          disabled={terms.loading || !terms.data?.terms.length}
        >
          <option value="" disabled>
            {terms.loading ? 'Loading terms…' : 'Select term'}
          </option>
          {terms.data?.terms.map((term) => (
            <option key={term.id} value={term.id}>
              {term.name} - {term.status}
            </option>
          ))}
        </Select>
        {selectedTerm && (
          <StatusBadge
            tone={selectedTerm.status === 'planning' ? 'warning' : 'neutral'}
          >
            {selectedTerm.code} - {selectedTerm.status}
          </StatusBadge>
        )}
      </div>

      <Section
        title="Resolver analytics"
        description="Live conflict state plus persisted resolution outcomes. Unavailable metrics are never estimated."
        actions={<BarChart3 size={18} />}
      >
        {analytics.loading ? (
          <LoadingState label="Loading resolver analytics" />
        ) : analytics.error ? (
          <ErrorState message={analytics.error} retry={analytics.reload} />
        ) : analytics.data ? (
          <>
            <div className="metric-grid">
              <Metric
                label="Confirmed conflicts"
                value={analytics.data.current_confirmed_conflicts}
                tone={analytics.data.current_confirmed_conflicts ? 'warning' : 'success'}
              />
              <Metric
                label="Structural clashes"
                value={analytics.data.current_structural_clashes}
                tone={analytics.data.current_structural_clashes ? 'danger' : 'success'}
              />
              <Metric label="Verified students" value={analytics.data.current_verified_students} />
              <Metric label="Reports" value={analytics.data.report_total} />
              <Metric label="Applied resolutions" value={analytics.data.resolution_applications} tone="success" />
              <Metric
                label="Undo rate"
                value={rateLabel(analytics.data.undo_rate.value)}
                hint={analytics.data.undo_rate.reason || undefined}
              />
              <Metric label="Shared resolutions" value={rateLabel(analytics.data.shared_resolution_percentage)} />
              <Metric
                label="Avg. first resolution"
                value={
                  analytics.data.average_first_resolution_hours === null
                    ? '—'
                    : `${analytics.data.average_first_resolution_hours}h`
                }
              />
            </div>
            <div className="insight-note">
              <strong>Recommendation acceptance</strong>
              <span>{rateLabel(analytics.data.recommendation_acceptance_rate.value)}</span>
              <p>
                {analytics.data.recommendation_acceptance_rate.reason ||
                  'Measured from persisted recommendation events.'}
              </p>
            </div>
            <p className="muted">
              Updated {formatRelative(analytics.data.generated_at)} · Term {analytics.data.term_code}
            </p>
          </>
        ) : null}
      </Section>

      <Section
        title="Data-quality diagnostics"
        description={
          selectedTerm?.status === 'planning'
            ? 'Planning-term readiness includes offerings, allocation, rooms, teaching profiles, true availability and generated-entry integrity.'
            : 'Actionable read-only findings. Nothing on this page repairs or deletes institutional data automatically.'
        }
        actions={<ShieldAlert size={18} />}
      >
        {quality.loading ? (
          <LoadingState label="Running data-quality checks" />
        ) : quality.error ? (
          <ErrorState message={quality.error} retry={quality.reload} />
        ) : quality.data ? (
          <>
            <div className="metric-grid">
              <Metric label="Total findings" value={quality.data.summary.total} />
              <Metric label="Critical" value={quality.data.summary.critical} tone={quality.data.summary.critical ? 'danger' : 'success'} />
              <Metric label="Errors" value={quality.data.summary.error} tone={quality.data.summary.error ? 'danger' : 'success'} />
              <Metric label="Warnings" value={quality.data.summary.warning} tone={quality.data.summary.warning ? 'warning' : 'success'} />
              {selectedTerm?.status === 'planning' && (
                <Metric
                  label="Scheduling findings"
                  value={schedulingFindings}
                  tone={schedulingFindings ? 'warning' : 'success'}
                  hint="Structured scheduling readiness/integrity"
                />
              )}
            </div>

            {quality.data.issues.length ? (
              <div className="quality-list">
                {quality.data.issues.map((issue, index) => (
                  <article
                    key={`${issue.issue_code}-${issue.entity_id || 'group'}-${index}`}
                    className="quality-item"
                  >
                    <div className="quality-item__heading">
                      <strong>{titleCase(issue.issue_code)}</strong>
                      <StatusBadge tone={severityTone(issue.severity)}>
                        {titleCase(issue.severity)}
                      </StatusBadge>
                    </div>
                    <p>{issue.message}</p>
                    <small>
                      {titleCase(issue.entity_type)}
                      {issue.entity_id ? ` #${issue.entity_id}` : ''} · {titleCase(issue.scope)} scope
                      {isSchedulingIssue(issue.issue_code) ? ' · Scheduling readiness' : ''}
                    </small>
                    <div className="quality-item__suggestion">
                      <strong>Suggested correction</strong>
                      <span>{issue.suggested_correction}</span>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <EmptyState
                title="No data-quality findings"
                description="The configured checks found no issues for this term and global institutional identities."
              />
            )}
            <p className="muted">{quality.data.important_note}</p>
          </>
        ) : null}
      </Section>
    </div>
  )
}
