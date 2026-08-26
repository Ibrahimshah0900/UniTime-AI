import { ArrowRight, CheckCircle2, Clock3, FileText, Plus, RotateCcw, RotateCw, ShieldCheck, UsersRound } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { reportsApi } from '../api/reports'
import { historyApi } from '../api/operations'
import { studentApi } from '../api/student'
import { ApiError } from '../api/client'
import { Field, Input, Select, Textarea } from '../components/Form'
import { EmptyState, ErrorNote, ErrorState, LoadingState, Metric, Modal, PageHeader, Pagination, Section, StatusBadge, SuccessNote } from '../components/Ui'
import { useAuth } from '../features/auth/AuthContext'
import { useAsync } from '../hooks/useAsync'
import type {
  ClashReportCluster,
  ClashReportDetail,
  ClashReportResolutionReason,
  ClashReportStatus,
  ResolutionCandidate,
} from '../types/api'
import type { StudentScheduleChange } from '../types/operations'
import { formatClock, formatRelative, statusTone, titleCase } from '../utils/format'

const statuses: ClashReportStatus[] = ['submitted', 'under_review', 'resolved', 'rejected', 'duplicate']
const resolutionReasons: ClashReportResolutionReason[] = ['timetable_changed', 'enrollment_corrected', 'course_dropped', 'other_verified_correction']
const PAGE_SIZE = 20

function candidateTone(status: string) {
  if (status === 'SAFE') return 'success'
  if (status === 'CONDITIONALLY_SAFE') return 'warning'
  if (status === 'INSUFFICIENT_DATA') return 'neutral'
  return 'danger'
}

export function ClashReportsPage() {
  const { user } = useAuth()
  const reviewer = Boolean(user && ['coordinator', 'admin'].includes(user.role))
  const [mode, setMode] = useState<'queue' | 'clusters'>('queue')
  const [status, setStatus] = useState<ClashReportStatus | ''>('')
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<number | null>(null)
  const [selectedCluster, setSelectedCluster] = useState<ClashReportCluster | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [message, setMessage] = useState('')

  const reports = useAsync(
    () => reviewer ? reportsApi.queue(status, offset, PAGE_SIZE) : studentApi.clashReports(offset, PAGE_SIZE),
    [reviewer, status, offset],
  )
  const clusters = useAsync(
    async () => reviewer ? reportsApi.clusters(true, offset, PAGE_SIZE) : { clusters: [], total: 0, offset: 0, limit: PAGE_SIZE },
    [reviewer, offset],
  )
  const detail = useAsync(
    async () => selected ? (reviewer ? reportsApi.detail(selected) : studentApi.clashReport(selected)) : null,
    [selected, reviewer],
  )

  async function refreshCurrent(messageText?: string) {
    if (messageText) setMessage(messageText)
    const [, refreshedClusters] = await Promise.all([reports.reload(), clusters.reload(), detail.reload()])
    if (selectedCluster && refreshedClusters && !refreshedClusters.clusters.some((cluster) => cluster.conflict_fingerprint === selectedCluster.conflict_fingerprint)) setSelectedCluster(null)
  }

  const showingClusters = reviewer && mode === 'clusters'
  const total = showingClusters ? clusters.data?.total : reports.data?.total
  const currentOffset = showingClusters ? clusters.data?.offset : reports.data?.offset
  const limit = showingClusters ? clusters.data?.limit : reports.data?.limit

  return <div className="page">
    <PageHeader
      title={reviewer ? 'Student clash reports' : 'Clash reports'}
      description={reviewer ? 'Review verified student conflicts, compare deterministic safe resolution candidates, and apply only revalidated timetable changes.' : 'Submit timetable clashes without visiting the coordinator office, then track their status here.'}
      actions={!reviewer ? <button className="btn btn--primary" onClick={() => setCreateOpen(true)}><Plus size={16}/>New report</button> : undefined}
    />
    {message && <SuccessNote>{message}</SuccessNote>}

    {reviewer && <div className="toolbar">
      <div className="button-row" role="group" aria-label="Clash report view">
        <button className={`btn btn--secondary ${mode === 'queue' ? 'is-active' : ''}`} onClick={() => { setMode('queue'); setOffset(0); setSelected(null); setSelectedCluster(null) }}>Report queue</button>
        <button className={`btn btn--secondary ${mode === 'clusters' ? 'is-active' : ''}`} onClick={() => { setMode('clusters'); setOffset(0); setSelected(null); setSelectedCluster(null) }}>Conflict clusters</button>
      </div>
      {!showingClusters && <Field label="Status filter"><Select value={status} onChange={(event) => { setStatus(event.target.value as ClashReportStatus | ''); setOffset(0); setSelected(null); setSelectedCluster(null) }}><option value="">All statuses</option>{statuses.map((item) => <option key={item} value={item}>{titleCase(item)}</option>)}</Select></Field>}
    </div>}

    {showingClusters ? (
      clusters.loading ? <LoadingState/> : clusters.error ? <ErrorState message={clusters.error} retry={clusters.reload}/> : (clusters.data?.clusters.length || selected) ? <div className="case-layout">
        <Section className="case-list-section"><div className="case-list">{(clusters.data?.clusters ?? []).map((cluster) => {
          const reportId = cluster.open_report_ids[0] || cluster.report_ids[0]
          const active = selectedCluster?.conflict_fingerprint === cluster.conflict_fingerprint
          return <button key={cluster.conflict_fingerprint} className={`case-row ${active ? 'case-row--active' : ''}`} onClick={() => { setSelectedCluster(cluster); setSelected(reportId) }}>
            <div className="case-row__top"><strong>{cluster.reported_classes.map((item) => item.course_code).join(' ↔ ')}</strong><StatusBadge tone={cluster.current_timetable_overlap ? 'warning' : 'success'}>{cluster.current_timetable_overlap ? 'Overlap active' : 'Overlap cleared'}</StatusBadge></div>
            <span>{cluster.open_report_count} open · {cluster.report_count} report{cluster.report_count === 1 ? '' : 's'} · {cluster.verified_affected_student_count} verified affected</span>
            <small><UsersRound size={13}/>{titleCase(cluster.enrollment_coverage)} enrollment coverage</small>
          </button>
        })}</div></Section>
        <Section className="case-detail-section">{selected && detail.loading ? <LoadingState/> : detail.error ? <ErrorState message={detail.error}/> : detail.data ? <>
          {selectedCluster && <ClusterSummary cluster={selectedCluster}/>}<ReportDetail report={detail.data} reviewer onUpdated={refreshCurrent}/>
        </> : <EmptyState title="Select a conflict cluster" description="Choose an underlying conflict to inspect its reports, enrollment evidence and safe resolution candidates."/>}</Section>
      </div> : <EmptyState title="No open conflict clusters" description="No grouped student reports currently require coordinator action."/>
    ) : (
      reports.loading ? <LoadingState/> : reports.error ? <ErrorState message={reports.error} retry={reports.reload}/> : reports.data?.reports.length ? <div className="case-layout">
        <Section className="case-list-section"><div className="case-list">{reports.data.reports.map((report) => <button key={report.id} className={`case-row ${selected === report.id ? 'case-row--active' : ''}`} onClick={() => { setSelected(report.id); setSelectedCluster(null) }}><div className="case-row__top"><strong>#{report.id} {reviewer && `· ${report.student_name}`}</strong><StatusBadge tone={statusTone(report.status)}>{titleCase(report.status)}</StatusBadge></div><span>{report.items.map((item) => item.course_code).join(' ↔ ')}</span><small><Clock3 size={13}/>{formatRelative(report.created_at)}</small></button>)}</div></Section>
        <Section className="case-detail-section">{selected ? detail.loading ? <LoadingState/> : detail.error ? <ErrorState message={detail.error}/> : detail.data ? <ReportDetail report={detail.data} reviewer={reviewer} onUpdated={refreshCurrent}/> : null : <EmptyState title="Select a report" description="Choose a case from the queue to inspect its classes, notes, audit history and resolution state."/>}</Section>
      </div> : <EmptyState title={reviewer ? 'No reports in this queue' : 'No clash reports yet'} description={reviewer ? 'Try another status filter or check back when students submit new cases.' : 'If two of your enrolled classes overlap, create a report here.'} action={!reviewer ? <button className="btn btn--primary" onClick={() => setCreateOpen(true)}>Create report</button> : undefined}/>
    )}

    {typeof total === 'number' && typeof currentOffset === 'number' && typeof limit === 'number' && <Pagination total={total} offset={currentOffset} limit={limit} label={showingClusters ? 'clusters' : 'reports'} onChange={(next) => { setOffset(next); setSelected(null); setSelectedCluster(null) }}/>}
    {createOpen && <CreateReportModal onClose={() => setCreateOpen(false)} onCreated={async () => { setCreateOpen(false); setOffset(0); setMessage('Clash report submitted.'); await reports.reload() }}/>}
  </div>
}

function ClusterSummary({ cluster }: { cluster: ClashReportCluster }) {
  return <div className="cluster-summary">
    <div className="metric-grid">
      <Metric label="Open reports" value={cluster.open_report_count}/>
      <Metric label="Reporting students" value={cluster.reporting_student_count}/>
      <Metric label="Verified affected" value={cluster.verified_affected_student_count} tone="warning"/>
      <Metric label="Enrollment coverage" value={titleCase(cluster.enrollment_coverage)}/>
    </div>
    <p className="muted">Cluster groups the same term/fingerprint conflict without exposing student identity in the cluster payload.</p>
  </div>
}

function ReportDetail({ report, reviewer, onUpdated }: { report: ClashReportDetail; reviewer: boolean; onUpdated: (message?: string) => Promise<void> }) {
  const [reviewOpen, setReviewOpen] = useState(false)
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0)
  async function refreshAfterResolution(message?: string) {
    setHistoryRefreshKey(historyRefreshKey + 1)
    await onUpdated(message)
  }
  return <div className="case-detail">
    <div className="case-detail__heading"><div><span className="eyebrow">Case #{report.id}</span><h2>{report.items.map((item) => item.course_code).join(' ↔ ')}</h2>{reviewer && <p>{report.student_name} · {report.student_email || report.student_registration_number}</p>}</div><StatusBadge tone={statusTone(report.status)}>{titleCase(report.status)}</StatusBadge></div>
    <div className="case-classes">{report.items.map((item) => <article key={item.id}><strong>{item.course_code}</strong><span>{item.section ? `Section ${item.section}` : 'Shared session'}</span><small>{item.day || 'Day unavailable'} · {formatClock(item.start_time)} – {formatClock(item.end_time)}</small></article>)}</div>
    {report.notes && <div className="case-note"><FileText size={17}/><div><strong>Student notes</strong><p>{report.notes}</p></div></div>}
    {report.evidence_reference && <div className="case-note"><strong>Evidence reference</strong><p>{report.evidence_reference}</p></div>}
    {report.resolution_note && <div className="resolution-note"><CheckCircle2 size={17}/><div><strong>Resolution{report.resolution_reason ? ` · ${titleCase(report.resolution_reason)}` : ''}</strong><p>{report.resolution_note}</p></div></div>}

    {reviewer && ['submitted', 'under_review'].includes(report.status) && <ResolutionCandidates report={report} onUpdated={refreshAfterResolution}/>}
    {reviewer && <LinkedResolutionHistory key={report.updated_at} reportId={report.id} refreshKey={historyRefreshKey} onUpdated={onUpdated}/>}

    <div className="timeline"><h3>Case history</h3>{report.events.map((event) => <div className="timeline__item" key={event.id}><span/><div><strong>{titleCase(event.action)}</strong><p>{event.from_status && event.to_status ? `${titleCase(event.from_status)} → ${titleCase(event.to_status)}` : event.note || 'Case activity recorded'}</p><small>{formatRelative(event.created_at)}</small></div></div>)}</div>
    {reviewer && ['submitted', 'under_review'].includes(report.status) && <button className="btn btn--secondary" onClick={() => setReviewOpen(true)}>Update case status <ArrowRight size={16}/></button>}
    {reviewOpen && <ReviewModal report={report} onClose={() => setReviewOpen(false)} onSaved={async () => { setReviewOpen(false); await onUpdated('Clash report updated.') }}/>}
  </div>
}

function ResolutionCandidates({ report, onUpdated }: { report: ClashReportDetail; onUpdated: (message?: string) => Promise<void> }) {
  const candidates = useAsync(() => reportsApi.candidates(report.id, undefined, 20, 8), [report.id, report.updated_at])
  const [selectedCandidate, setSelectedCandidate] = useState<ResolutionCandidate | null>(null)

  return <Section title="Safe resolution candidates" description="Hard constraints are checked before ranking. The backend revalidates the selected move under the write lock before applying it." className="resolver-section">
    {report.status !== 'under_review' && <div className="resolver-gate"><ShieldCheck size={18}/><div><strong>Review gate</strong><p>Move this report to Under Review before an otherwise applicable candidate can be applied.</p></div></div>}
    {candidates.loading ? <LoadingState label="Generating deterministic candidates"/> : candidates.error ? <ErrorState message={candidates.error} retry={candidates.reload}/> : candidates.data ? <>
      <div className="candidate-summary">
        <StatusBadge tone="success">{candidates.data.summary.safe} safe</StatusBadge>
        <StatusBadge tone="warning">{candidates.data.summary.conditionally_safe} conditional</StatusBadge>
        <StatusBadge tone="neutral">{candidates.data.summary.insufficient_data} insufficient data</StatusBadge>
        <StatusBadge tone="danger">{candidates.data.summary.rejected} rejected</StatusBadge>
      </div>
      {candidates.data.candidates.length ? <div className="candidate-list">{candidates.data.candidates.map((candidate) => {
        const applicable = report.status === 'under_review' && candidate.status !== 'INSUFFICIENT_DATA'
        return <article className="candidate-card" key={candidate.candidate_id}>
          <div className="candidate-card__heading"><div><strong>{candidate.course_code || candidate.course_name || `Entry #${candidate.entry_id}`}</strong><small>Entry #{candidate.entry_id} · score {candidate.rank_score}</small></div><StatusBadge tone={candidateTone(candidate.status)}>{titleCase(candidate.status)}</StatusBadge></div>
          <div className="candidate-move"><span>{candidate.move_from.day} · {formatClock(candidate.move_from.start_time)}–{formatClock(candidate.move_from.end_time)}</span><ArrowRight size={15}/><strong>{candidate.move_to.day} · {formatClock(candidate.move_to.start_time)}–{formatClock(candidate.move_to.end_time)}</strong></div>
          <div className="candidate-impact"><span>Affected students <strong>{candidate.impact.affected_students}</strong></span><span>Confirmed conflicts <strong>{candidate.impact.confirmed_conflicts_before} → {candidate.impact.confirmed_conflicts_after}</strong></span><span>Structural clashes <strong>{candidate.impact.structural_clashes_before} → {candidate.impact.structural_clashes_after}</strong></span></div>
          {candidate.missing_data.length > 0 && <div className="candidate-limitations"><strong>Metadata limitations</strong><ul>{candidate.missing_data.map((item) => <li key={item}>{item}</li>)}</ul></div>}
          <details><summary>Safety checks & score explanation</summary><div className="candidate-checks">{candidate.checks.map((check) => <div key={check.name}><StatusBadge tone={check.status === 'PASS' ? 'success' : check.status === 'WARN' ? 'warning' : 'danger'}>{check.status}</StatusBadge><span>{check.detail}</span></div>)}</div><ul>{candidate.score_components.map((component) => <li key={component.signal}>{component.explanation}</li>)}</ul></details>
          <button className="btn btn--primary" disabled={!applicable} onClick={() => setSelectedCandidate(candidate)}>{candidate.status === 'INSUFFICIENT_DATA' ? 'Not applicable — missing data' : report.status !== 'under_review' ? 'Start review before applying' : candidate.status === 'CONDITIONALLY_SAFE' ? 'Review & apply conditional move' : 'Review & apply safe move'}</button>
        </article>
      })}</div> : <EmptyState title="No applicable candidates" description="The current hard constraints did not produce a move that can safely resolve this report."/>}
      {candidates.data.rejected_candidates.length > 0 && <details className="rejected-candidates"><summary>Show rejected candidate examples ({candidates.data.rejected_candidates.length})</summary>{candidates.data.rejected_candidates.map((candidate) => <article key={candidate.candidate_id}><strong>Entry #{candidate.entry_id} → {candidate.move_to.day} {formatClock(candidate.move_to.start_time)}</strong><ul>{candidate.rejection_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></article>)}</details>}
      <p className="muted">{candidates.data.important_note}</p>
    </> : null}
    {selectedCandidate && <ApplyCandidateModal report={report} candidate={selectedCandidate} onClose={() => setSelectedCandidate(null)} onApplied={async (resolvedCount, changeId) => { setSelectedCandidate(null); await onUpdated(`Resolution applied. ${resolvedCount} related report${resolvedCount === 1 ? '' : 's'} resolved after live verification. Change #${changeId} is available for undo/redo.`) }}/>}
  </Section>
}

function ApplyCandidateModal({ report, candidate, onClose, onApplied }: { report: ClashReportDetail; candidate: ResolutionCandidate; onClose: () => void; onApplied: (resolvedCount: number, changeId: number) => Promise<void> }) {
  const [note, setNote] = useState('')
  const [confirmConditional, setConfirmConditional] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const conditional = candidate.status === 'CONDITIONALLY_SAFE'

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!note.trim()) { setError('A resolution note is required.'); return }
    if (conditional && !confirmConditional) { setError('Confirm the listed metadata limitations before applying this conditional candidate.'); return }
    setBusy(true); setError('')
    try {
      const result = await reportsApi.applyCandidate(report.id, candidate.candidate_id, {
        target_entry_id: candidate.entry_id,
        resolution_note: note,
        confirm_conditional: conditional ? confirmConditional : false,
      })
      await onApplied(result.resolved_report_count, result.change_id)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to apply the resolution candidate.')
    } finally { setBusy(false) }
  }

  return <Modal title={`Apply resolution for case #${report.id}`} onClose={onClose} wide><form className="form-stack" onSubmit={submit}>
    <div className="candidate-move candidate-move--modal"><span>{candidate.move_from.day} · {formatClock(candidate.move_from.start_time)}–{formatClock(candidate.move_from.end_time)}</span><ArrowRight size={16}/><strong>{candidate.move_to.day} · {formatClock(candidate.move_to.start_time)}–{formatClock(candidate.move_to.end_time)}</strong></div>
    <div className="candidate-impact"><span>Affected students <strong>{candidate.impact.affected_students}</strong></span><span>Confirmed conflicts removed <strong>{candidate.impact.confirmed_conflicts_removed}</strong></span><span>New confirmed conflicts <strong>{candidate.impact.new_confirmed_conflicts}</strong></span></div>
    {candidate.missing_data.length > 0 && <div className="candidate-limitations"><strong>Known limitations</strong><ul>{candidate.missing_data.map((item) => <li key={item}>{item}</li>)}</ul></div>}
    {conditional && <label className="confirmation-row"><input type="checkbox" checked={confirmConditional} onChange={(event) => setConfirmConditional(event.target.checked)}/><span>I reviewed the metadata limitations and explicitly confirm this conditionally safe candidate.</span></label>}
    <Field label="Resolution note" hint="Stored on every related report that is verified resolved by this timetable change."><Textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={2000} rows={4} placeholder="Explain why this timetable move is being approved."/></Field>
    {error && <ErrorNote>{error}</ErrorNote>}
    <div className="modal-actions"><button type="button" className="btn btn--secondary" onClick={onClose}>Cancel</button><button className="btn btn--primary" disabled={busy}>{busy ? 'Revalidating & applying…' : 'Apply after live revalidation'}</button></div>
  </form></Modal>
}

function LinkedResolutionHistory({ reportId, refreshKey, onUpdated }: { reportId: number; refreshKey: number; onUpdated: (message?: string) => Promise<void> }) {
  const history = useAsync(() => historyApi.studentChanges(), [reportId, refreshKey])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const linked = useMemo(() => {
    const items = history.data?.changes.filter((change) => change.report_id === reportId) || []
    return items.sort((a, b) => b.id - a.id)[0] || null
  }, [history.data, reportId])

  if (history.loading || !linked) return null

  async function act(mode: 'undo' | 'redo', change: StudentScheduleChange) {
    setBusy(true); setError('')
    try {
      if (mode === 'undo') await historyApi.undoStudentChange(change.id)
      else await historyApi.redoStudentChange(change.id)
      await history.reload()
      await onUpdated(mode === 'undo' ? 'Resolution undone. Any restored personal conflicts were reopened after live verification.' : 'Resolution safely redone after candidate revalidation.')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : `Unable to ${mode} resolution.`)
    } finally { setBusy(false) }
  }

  return <div className="linked-resolution-history"><div><strong>Linked timetable resolution · change #{linked.id}</strong><span>{linked.old_day} {formatClock(linked.old_start_time)}–{formatClock(linked.old_end_time)} → {linked.new_day} {formatClock(linked.new_start_time)}–{formatClock(linked.new_end_time)}</span><small>{linked.safety_status ? `${titleCase(linked.safety_status)} · ` : ''}{linked.undone ? 'Currently undone' : 'Currently applied'}</small></div>{linked.undone ? <button className="btn btn--secondary" disabled={busy} onClick={() => void act('redo', linked)}><RotateCw size={15}/>{busy ? 'Revalidating…' : 'Safe redo'}</button> : <button className="btn btn--secondary" disabled={busy} onClick={() => void act('undo', linked)}><RotateCcw size={15}/>{busy ? 'Undoing…' : 'Undo resolution'}</button>}{error && <ErrorNote>{error}</ErrorNote>}</div>
}

function CreateReportModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => Promise<void> }) {
  const timetable = useAsync(() => studentApi.timetable(), [])
  const [selected, setSelected] = useState<number[]>([])
  const [notes, setNotes] = useState('')
  const [evidence, setEvidence] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const selectedEntries = useMemo(() => (timetable.data || []).filter((entry) => selected.includes(entry.id)), [timetable.data, selected])
  function toggle(id: number) { setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : current.length < 10 ? [...current, id] : current) }
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (selected.length < 2) { setError('Select at least two timetable entries.'); return }
    setBusy(true); setError('')
    try { await studentApi.submitClashReport({ timetable_entry_ids: selected, notes: notes || null, evidence_reference: evidence || null }); await onCreated() }
    catch (err) { setError(err instanceof ApiError ? err.message : 'Unable to submit report.') }
    finally { setBusy(false) }
  }
  return <Modal title="Report a timetable clash" onClose={onClose} wide><form className="form-stack" onSubmit={submit}><div><strong>Select 2–10 classes</strong><p className="muted">The backend verifies that every selected class belongs to your personal timetable and that at least one pair overlaps.</p></div>{timetable.loading ? <LoadingState/> : <div className="selectable-classes">{timetable.data?.map((entry) => <label key={entry.id} className={selected.includes(entry.id) ? 'selected' : ''}><input type="checkbox" checked={selected.includes(entry.id)} onChange={() => toggle(entry.id)}/><div><strong>{entry.course_code || entry.course_name}</strong><span>{entry.day} · {formatClock(entry.start_time)} – {formatClock(entry.end_time)}</span><small>{entry.section ? `Section ${entry.section}` : 'Shared'} · {entry.room || 'Room TBA'}</small></div></label>)}</div>}<Field label="Notes"><Textarea value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={2000} rows={4} placeholder="Explain what clashes and how it affects you."/></Field><Field label="Evidence reference" hint="Optional text/reference only; the backend contract does not expose file upload for report evidence."><Input value={evidence} onChange={(e) => setEvidence(e.target.value)} maxLength={500}/></Field>{selectedEntries.length > 0 && <small className="muted">Selected: {selectedEntries.map((entry) => entry.course_code).join(', ')}</small>}{error && <ErrorNote>{error}</ErrorNote>}<div className="modal-actions"><button type="button" className="btn btn--secondary" onClick={onClose}>Cancel</button><button className="btn btn--primary" disabled={busy}>{busy ? 'Submitting…' : 'Submit report'}</button></div></form></Modal>
}

function ReviewModal({ report, onClose, onSaved }: { report: ClashReportDetail; onClose: () => void; onSaved: () => Promise<void> }) {
  const allowed: ClashReportStatus[] = report.status === 'submitted' ? ['under_review', 'rejected', 'duplicate'] : ['resolved', 'rejected', 'duplicate']
  const [status, setStatus] = useState<ClashReportStatus>(allowed[0])
  const [reason, setReason] = useState<ClashReportResolutionReason>('timetable_changed')
  const [note, setNote] = useState('')
  const [duplicateId, setDuplicateId] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const terminal = ['resolved', 'rejected', 'duplicate'].includes(status)
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (terminal && !note.trim()) { setError('A resolution note is required for terminal statuses.'); return }
    if (status === 'duplicate' && !Number(duplicateId)) { setError('Duplicate reports require the original report ID.'); return }
    setBusy(true); setError('')
    try { await reportsApi.review(report.id, { status, resolution_note: terminal ? note : null, resolution_reason: status === 'resolved' ? reason : null, duplicate_of_report_id: status === 'duplicate' ? Number(duplicateId) : null }); await onSaved() }
    catch (err) { setError(err instanceof ApiError ? err.message : 'Unable to update report.') }
    finally { setBusy(false) }
  }
  return <Modal title={`Update case #${report.id}`} onClose={onClose}><form className="form-stack" onSubmit={submit}><Field label="Next status"><Select value={status} onChange={(e) => setStatus(e.target.value as ClashReportStatus)}>{allowed.map((item) => <option key={item} value={item}>{titleCase(item)}</option>)}</Select></Field>{status === 'resolved' && <Field label="Verified resolution reason" hint="The backend checks this reason against the student's live timetable and enrollments."><Select value={reason} onChange={(e) => setReason(e.target.value as ClashReportResolutionReason)}>{resolutionReasons.map((item) => <option key={item} value={item}>{titleCase(item)}</option>)}</Select></Field>}{status === 'duplicate' && <Field label="Original report ID"><Input type="number" min={1} value={duplicateId} onChange={(e) => setDuplicateId(e.target.value)} required/></Field>}<Field label={terminal ? 'Resolution note' : 'Review note'}><Textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} rows={4}/></Field>{error && <ErrorNote>{error}</ErrorNote>}<div className="modal-actions"><button type="button" className="btn btn--secondary" onClick={onClose}>Cancel</button><button className="btn btn--primary" disabled={busy}>Save status</button></div></form></Modal>
}
