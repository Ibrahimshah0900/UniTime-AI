import {
  History as HistoryIcon,
  Play,
  RotateCcw,
  RotateCw,
  Sparkles,
  TriangleAlert,
  Wrench,
} from 'lucide-react'
import { useState } from 'react'
import { ApiError } from '../api/client'
import { clashesApi, historyApi, optimizerApi } from '../api/operations'
import { termsApi } from '../api/terms'
import { Field, Input, Select } from '../components/Form'
import {
  EmptyState,
  ErrorNote,
  ErrorState,
  LoadingState,
  Metric,
  PageHeader,
  Section,
  StatusBadge,
  SuccessNote,
} from '../components/Ui'
import { useAsync } from '../hooks/useAsync'
import type {
  AuditItem,
  ClashEntry,
  OptimizerMove,
  StudentMove,
  StudentScheduleChange,
  TimetableChange,
  TimeSlot,
} from '../types/operations'
import { formatClock, formatRelative, titleCase } from '../utils/format'

function operationError(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback
}

function tone(value: string) {
  const normalized = value.toLowerCase()
  if (['completed', 'active', 'available', 'resolved', 'safe'].includes(normalized)) return 'success'
  if (['critical', 'failed', 'rejected'].includes(normalized)) return 'danger'
  if (['confirmed', 'probable', 'warning', 'partial'].includes(normalized)) return 'warning'
  if (['running', 'possible'].includes(normalized)) return 'info'
  return 'neutral'
}

function entryLabel(entry: ClashEntry) {
  return entry.course_code || entry.course_name || `Entry #${entry.id}`
}

function slotLabel(slot: TimeSlot) {
  return `${slot.day} · ${formatClock(slot.start_time)}–${formatClock(slot.end_time)}`
}

function MoveSummary({ move }: { move: StudentMove | OptimizerMove }) {
  return (
    <div className="move-summary">
      <div>
        <span>Move</span>
        <strong>{move.course_code || move.course_name || `Entry #${move.entry_id}`}</strong>
        <small>{slotLabel(move.move_from)} → {slotLabel(move.move_to)}</small>
      </div>
      <div>
        <span>Room</span>
        <StatusBadge tone={tone(move.room_status)}>{titleCase(move.room_status)}</StatusBadge>
      </div>
      <div>
        <span>Score</span>
        <strong>{'global_score' in move ? move.global_score : move.score}</strong>
      </div>
    </div>
  )
}

export function ClashesPage() {
  const terms = useAsync(() => termsApi.list(), [])
  const [selectedTermId, setSelectedTermId] = useState<number | null>(null)
  const effectiveTermId = selectedTermId ?? terms.data?.active_term_id ?? terms.data?.terms[0]?.id ?? null
  const selectedTerm = terms.data?.terms.find((term) => term.id === effectiveTermId) ?? null
  const canApplySelectedTerm = selectedTerm?.status === 'active'
  const clashes = useAsync(() => clashesApi.all(effectiveTermId), [effectiveTermId])
  const rooms = useAsync(() => clashesApi.roomSuggestions(effectiveTermId), [effectiveTermId])
  const risk = useAsync(() => clashesApi.studentRisk(effectiveTermId), [effectiveTermId])
  const groups = useAsync(() => clashesApi.studentGroups(effectiveTermId), [effectiveTermId])
  const resolutions = useAsync(() => clashesApi.studentResolutions(effectiveTermId), [effectiveTermId])
  const [message, setMessage] = useState('')
  const [actionError, setActionError] = useState('')
  const [busyRoom, setBusyRoom] = useState<number | null>(null)
  const [busyGroup, setBusyGroup] = useState<number | null>(null)
  const roomClashes = clashes.data?.clashes.filter((clash) => clash.type === 'room') || []

  async function reloadAnalysis() {
    await Promise.all([
      clashes.reload(),
      rooms.reload(),
      risk.reload(),
      groups.reload(),
      resolutions.reload(),
    ])
  }

  async function applyRoom(index: number) {
    const clash = roomClashes[index]
    const fix = rooms.data?.resolutions[index]?.best_fix
    if (!canApplySelectedTerm || !clash || !fix || busyRoom !== null) return
    if (!window.confirm(`Move ${fix.course_code || `entry #${fix.entry_id}`} from ${fix.from_room || 'unassigned'} to ${fix.to_room}?`)) return
    setBusyRoom(index)
    setMessage('')
    setActionError('')
    try {
      await clashesApi.applyRoomFix(clash.entry_1.id, clash.entry_2.id)
      setMessage('The validated room fix was applied and the analysis was refreshed.')
      await reloadAnalysis()
    } catch (error) {
      setActionError(operationError(error, 'Unable to apply the room fix.'))
    } finally {
      setBusyRoom(null)
    }
  }

  async function applyGroup(groupId: number) {
    const resolution = resolutions.data?.resolutions.find((item) => item.group_id === groupId)
    if (!canApplySelectedTerm || !resolution?.best_fix || busyGroup !== null) return
    if (!window.confirm(`Apply the best validated move for conflict group #${groupId}?`)) return
    setBusyGroup(groupId)
    setMessage('')
    setActionError('')
    try {
      await clashesApi.applyStudentGroupFix(groupId)
      setMessage(`Conflict group #${groupId} was updated and the analysis was refreshed.`)
      await reloadAnalysis()
    } catch (error) {
      setActionError(operationError(error, 'Unable to apply the student conflict fix.'))
    } finally {
      setBusyGroup(null)
    }
  }

  return (
    <div className="page">
      <PageHeader
        title="Clash management"
        description="Review structural conflicts and cohort-risk signals, then apply only backend-validated fixes."
      />
      {message && <SuccessNote>{message}</SuccessNote>}
      {actionError && <ErrorNote>{actionError}</ErrorNote>}
      {terms.error && <ErrorNote>{terms.error}</ErrorNote>}
      <div className="toolbar">
        <Select aria-label="Academic term" value={effectiveTermId ? String(effectiveTermId) : ''} onChange={(event) => setSelectedTermId(Number(event.target.value))} disabled={terms.loading || !terms.data?.terms.length}>
          <option value="" disabled>{terms.loading ? 'Loading terms…' : 'Select term'}</option>
          {terms.data?.terms.map((term) => <option key={term.id} value={term.id}>{term.name} - {term.status}</option>)}
        </Select>
        {selectedTerm && <span className="muted">{selectedTerm.code} - {selectedTerm.status}{canApplySelectedTerm ? '' : ' - analysis only'}</span>}
      </div>

      <div className="metric-grid">
        <Metric label="Structural clashes" value={clashes.data?.total ?? '—'} tone={clashes.data?.total ? 'danger' : 'success'} />
        <Metric label="Room clashes" value={rooms.data?.room_clashes ?? '—'} tone={rooms.data?.room_clashes ? 'warning' : 'success'} />
        <Metric label="Confirmed cohort risks" value={risk.data?.summary.confirmed ?? '—'} tone={risk.data?.summary.confirmed ? 'danger' : 'success'} />
        <Metric label="Conflict groups" value={groups.data?.summary.total_groups ?? '—'} tone={groups.data?.summary.total_groups ? 'warning' : 'success'} />
      </div>

      <Section title="Detected structural clashes" description="Each row identifies the conflicting timetable entries and the shared resource causing the conflict.">
        {clashes.loading ? <LoadingState label="Detecting clashes" /> : clashes.error ? <ErrorState message={clashes.error} retry={clashes.reload} /> : clashes.data?.clashes.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>Type</th><th>Entries</th><th>When</th><th>Resource</th><th>Reason</th></tr></thead>
              <tbody>{clashes.data.clashes.map((clash, index) => (
                <tr key={`${clash.type}-${clash.entry_1.id}-${clash.entry_2.id}-${index}`}>
                  <td><StatusBadge tone={tone(clash.severity)}>{titleCase(clash.type)}</StatusBadge><small>{titleCase(clash.severity)}</small></td>
                  <td><strong>{entryLabel(clash.entry_1)} ↔ {entryLabel(clash.entry_2)}</strong><small>Entries #{clash.entry_1.id} and #{clash.entry_2.id}</small></td>
                  <td>{clash.day}<small>{formatClock(clash.entry_1.start_time)}–{formatClock(clash.entry_1.end_time)} / {formatClock(clash.entry_2.start_time)}–{formatClock(clash.entry_2.end_time)}</small></td>
                  <td>{clash.type === 'room' ? clash.entry_1.room : clash.entry_1.faculty}</td>
                  <td>{clash.reason}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        ) : <EmptyState title="No structural clashes" description="No overlapping room or faculty assignments were detected." />}
      </Section>

      <Section title="Validated room fixes" description="Apply a ranked alternative directly from its clash; no timetable IDs need to be copied manually.">
        {rooms.loading ? <LoadingState label="Finding room alternatives" /> : rooms.error ? <ErrorState message={rooms.error} retry={rooms.reload} /> : rooms.data?.resolutions.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>Clash</th><th>Recommended move</th><th>Score</th><th>Why it is safe</th><th>Action</th></tr></thead>
              <tbody>{rooms.data.resolutions.map((resolution, index) => {
                const fix = resolution.best_fix
                const clash = roomClashes[index]
                return (
                  <tr key={`${resolution.day}-${index}`}>
                    <td><strong>{resolution.day}</strong><small>{resolution.reason}</small></td>
                    <td>{fix ? <><strong>{fix.course_code || fix.course_name || `Entry #${fix.entry_id}`}</strong><small>{fix.from_room || 'Unassigned'} → {fix.to_room} · {formatClock(fix.start_time)}–{formatClock(fix.end_time)}</small></> : 'No safe move found'}</td>
                    <td>{fix?.score ?? '—'}</td>
                    <td>{fix?.reasons.slice(0, 2).join(' · ') || resolution.error || 'No candidate currently satisfies the safety rules.'}</td>
                    <td><button className="btn btn--secondary" disabled={!canApplySelectedTerm || !fix || !clash || busyRoom !== null} onClick={() => void applyRoom(index)}><Wrench size={15}/>{busyRoom === index ? 'Applying…' : 'Apply fix'}</button></td>
                  </tr>
                )
              })}</tbody>
            </table>
          </div>
        ) : <EmptyState title="No room fixes needed" description="There are no room clashes requiring resolution in this academic term." />}
      </Section>

      <div className="two-column">
        <Section title="Student/cohort risk signals" description={risk.data?.summary.important_note}>
          {risk.loading ? <LoadingState label="Analyzing cohort risk" /> : risk.error ? <ErrorState message={risk.error} retry={risk.reload} /> : risk.data?.risks.length ? (
            <div className="compact-list">{risk.data.risks.map((item, index) => (
              <article key={`${item.entry_1.id}-${item.entry_2.id}-${index}`}>
                <div><strong>{entryLabel(item.entry_1)} ↔ {entryLabel(item.entry_2)}</strong><span>{item.day} · {item.overlap.entry_1_time} / {item.overlap.entry_2_time}</span><small>{item.evidence.join(' · ')}</small></div>
                <div><StatusBadge tone={tone(item.risk_level)}>{titleCase(item.risk_level)}</StatusBadge><strong>{item.score}</strong></div>
              </article>
            ))}</div>
          ) : <EmptyState title="No cohort-risk signals" description="No inferred overlapping course risks were found." />}
        </Section>

        <Section title="Student conflict groups" description={groups.data?.summary.important_note}>
          {groups.loading || resolutions.loading ? <LoadingState label="Grouping conflicts" /> : groups.error ? <ErrorState message={groups.error} retry={groups.reload} /> : resolutions.error ? <ErrorState message={resolutions.error} retry={resolutions.reload} /> : groups.data?.groups.length ? (
            <div className="compact-list">{groups.data.groups.map((group) => {
              const resolution = resolutions.data?.resolutions.find((item) => item.group_id === group.group_id)
              return (
                <article key={group.group_id}>
                  <div><strong>Group #{group.group_id} · {group.entries.map(entryLabel).join(' ↔ ')}</strong><span>{group.day} · {formatClock(group.time_window.start_time)}–{formatClock(group.time_window.end_time)}</span><small>{resolution?.best_fix ? slotLabel(resolution.best_fix.move_to) : 'No safe candidate currently available'}</small></div>
                  <div className="compact-list__actions"><StatusBadge tone={tone(group.risk_level)}>{titleCase(group.risk_level)}</StatusBadge><button className="btn btn--secondary" disabled={!canApplySelectedTerm || !resolution?.best_fix || busyGroup !== null} onClick={() => void applyGroup(group.group_id)}><TriangleAlert size={15}/>{busyGroup === group.group_id ? 'Applying…' : 'Apply best'}</button></div>
                </article>
              )
            })}</div>
          ) : <EmptyState title="No conflict groups" description="No confirmed or probable cohort-risk groups require review." />}
        </Section>
      </div>
    </div>
  )
}

export function OptimizerPage() {
  const terms = useAsync(() => termsApi.list(), [])
  const [selectedTermId, setSelectedTermId] = useState<number | null>(null)
  const effectiveTermId = selectedTermId ?? terms.data?.active_term_id ?? terms.data?.terms[0]?.id ?? null
  const selectedTerm = terms.data?.terms.find((term) => term.id === effectiveTermId) ?? null
  const canApplySelectedTerm = selectedTerm?.status === 'active'
  const [maxSteps, setMaxSteps] = useState(5)
  const global = useAsync(() => optimizerApi.global(20, effectiveTermId), [effectiveTermId])
  const plan = useAsync(() => optimizerApi.plan(maxSteps, effectiveTermId), [maxSteps, effectiveTermId])
  const executions = useAsync(() => optimizerApi.executions(effectiveTermId), [effectiveTermId])
  const [selectedExecutionId, setSelectedExecutionId] = useState('')
  const execution = useAsync(async () => selectedExecutionId ? optimizerApi.execution(selectedExecutionId) : null, [selectedExecutionId])
  const [message, setMessage] = useState('')
  const [actionError, setActionError] = useState('')
  const [busy, setBusy] = useState('')

  async function refreshOptimizer() {
    await Promise.all([global.reload(), plan.reload(), executions.reload()])
    if (selectedExecutionId) await execution.reload()
  }

  async function applyGlobal() {
    if (!canApplySelectedTerm || !global.data?.best_move || busy) return
    if (!window.confirm('Apply the backend-ranked best global optimizer move?')) return
    setBusy('global')
    setMessage('')
    setActionError('')
    try {
      await optimizerApi.applyGlobalBest()
      setMessage('The best global move was applied safely.')
      await refreshOptimizer()
    } catch (error) {
      setActionError(operationError(error, 'Unable to apply the optimizer move.'))
    } finally {
      setBusy('')
    }
  }

  async function applyPlan() {
    if (!canApplySelectedTerm || !plan.data?.planned_steps || busy) return
    if (!window.confirm(`Apply this ${plan.data.planned_steps}-step optimizer plan?`)) return
    setBusy('plan')
    setMessage('')
    setActionError('')
    try {
      await optimizerApi.applyPlan(maxSteps)
      setMessage('The multi-step optimizer plan was applied.')
      await refreshOptimizer()
    } catch (error) {
      setActionError(operationError(error, 'Unable to apply the optimizer plan.'))
    } finally {
      setBusy('')
    }
  }

  async function rollback(mode: 'undo' | 'redo') {
    if (!canApplySelectedTerm || !selectedExecutionId || busy) return
    if (!window.confirm(`${mode === 'undo' ? 'Undo' : 'Redo'} optimizer execution ${selectedExecutionId}?`)) return
    setBusy(mode)
    setMessage('')
    setActionError('')
    try {
      if (mode === 'undo') await optimizerApi.undoExecution(selectedExecutionId)
      else await optimizerApi.redoExecution(selectedExecutionId)
      setMessage(`Optimizer execution ${mode} completed.`)
      await refreshOptimizer()
    } catch (error) {
      setActionError(operationError(error, `Unable to ${mode} the optimizer execution.`))
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="page">
      <PageHeader title="Optimizer" description="Review deterministic timetable improvements and their safety impact before applying any mutation." />
      {message && <SuccessNote>{message}</SuccessNote>}
      {actionError && <ErrorNote>{actionError}</ErrorNote>}
      {terms.error && <ErrorNote>{terms.error}</ErrorNote>}
      <div className="toolbar">
        <Select aria-label="Academic term" value={effectiveTermId ? String(effectiveTermId) : ''} onChange={(event) => { setSelectedTermId(Number(event.target.value)); setSelectedExecutionId('') }} disabled={terms.loading || !terms.data?.terms.length}>
          <option value="" disabled>{terms.loading ? 'Loading terms…' : 'Select term'}</option>
          {terms.data?.terms.map((term) => <option key={term.id} value={term.id}>{term.name} - {term.status}</option>)}
        </Select>
        {selectedTerm && <span className="muted">{selectedTerm.code} - {selectedTerm.status}{canApplySelectedTerm ? '' : ' - analysis only'}</span>}
      </div>

      <div className="optimizer-hero">
        <div>
          <span className="eyebrow">Read-only analysis</span>
          <h2>Global optimizer</h2>
          <p>The backend evaluates each candidate against the complete timetable and rejects moves that worsen structural clashes or cohort risk.</p>
          <button className="btn btn--primary" disabled={!canApplySelectedTerm || !global.data?.best_move || Boolean(busy)} onClick={() => void applyGlobal()}><Sparkles size={16}/>{busy === 'global' ? 'Applying…' : 'Apply best move'}</button>
        </div>
        <div>{global.loading ? <LoadingState label="Ranking moves" /> : global.error ? <ErrorState message={global.error} retry={global.reload} /> : global.data ? (
          <div className="optimizer-overview">
            <div className="optimizer-stats"><div><span>Generated</span><strong>{global.data.candidate_summary.generated}</strong></div><div><span>Globally safe</span><strong>{global.data.candidate_summary.globally_safe}</strong></div><div><span>Rejected</span><strong>{global.data.candidate_summary.rejected}</strong></div></div>
            {global.data.best_move ? <MoveSummary move={global.data.best_move} /> : <p className="data-empty">No safe beneficial move is currently available.</p>}
          </div>
        ) : null}</div>
      </div>

      <Section title="Ranked global moves" description="The highest scoring safe candidates are shown first.">
        {global.data?.ranked_moves.length ? (
          <div className="table-wrap"><table className="data-table"><thead><tr><th>Rank</th><th>Class</th><th>Move</th><th>Impact</th><th>Room</th><th>Score</th></tr></thead><tbody>{global.data.ranked_moves.map((move, index) => (
            <tr key={`${move.entry_id}-${move.move_to.day}-${move.move_to.start_time}`}><td>#{index + 1}</td><td><strong>{move.course_code || move.course_name || `Entry #${move.entry_id}`}</strong><small>{move.section || 'Shared'} · {move.faculty || 'Faculty TBA'}</small></td><td>{slotLabel(move.move_from)}<small>→ {slotLabel(move.move_to)}</small></td><td><strong>{move.improvement.student_risk_cost.reduction} risk-cost reduction</strong><small>{move.improvement.general_clashes.reduction} structural · {move.improvement.student_groups.reduction} groups</small></td><td><StatusBadge tone={tone(move.room_status)}>{titleCase(move.room_status)}</StatusBadge></td><td>{move.global_score}</td></tr>
          ))}</tbody></table></div>
        ) : !global.loading && !global.error ? <EmptyState title="No ranked moves" description="The current timetable has no safe beneficial optimizer candidate." /> : null}
      </Section>

      <div className="two-column">
        <Section title="Multi-step plan" description="Every step is recalculated against the simulated result of the preceding steps." actions={<Field label="Max steps"><Input type="number" min={1} max={20} value={maxSteps} onChange={(event) => setMaxSteps(Math.min(20, Math.max(1, Number(event.target.value) || 1)))} /></Field>}>
          {plan.loading ? <LoadingState label="Building plan" /> : plan.error ? <ErrorState message={plan.error} retry={plan.reload} /> : plan.data ? (
            <>
              <div className="plan-summary"><div><span>Planned</span><strong>{plan.data.planned_steps}</strong></div><div><span>Risk cost reduced</span><strong>{plan.data.overall_improvement.student_risk_cost.reduction}</strong></div><div><span>Clashes reduced</span><strong>{plan.data.overall_improvement.general_clashes.reduction}</strong></div></div>
              {plan.data.steps.length ? <ol className="plan-steps">{plan.data.steps.map((step) => <li key={step.step}><MoveSummary move={step} /></li>)}</ol> : <EmptyState title="No steps proposed" description={plan.data.stop_reason || 'No safe plan is available.'} />}
              <div className="section-footer"><button className="btn btn--primary" disabled={!canApplySelectedTerm || !plan.data.planned_steps || Boolean(busy)} onClick={() => void applyPlan()}><Play size={16}/>{busy === 'plan' ? 'Applying…' : `Apply ${plan.data.planned_steps}-step plan`}</button></div>
            </>
          ) : null}
        </Section>

        <Section title="Execution history" description="Select a grouped optimizer run to inspect it or perform a controlled rollback.">
          {executions.loading ? <LoadingState label="Loading executions" /> : executions.error ? <ErrorState message={executions.error} retry={executions.reload} /> : executions.data?.executions.length ? (
            <div className="execution-list">{executions.data.executions.map((item) => <button key={item.execution_id} className={selectedExecutionId === item.execution_id ? 'selected' : ''} onClick={() => setSelectedExecutionId(item.execution_id)}><div><strong>{item.execution_id}</strong><span>{item.applied_steps} of {item.requested_steps} steps · {item.created_at ? formatRelative(item.created_at) : 'Time unavailable'}</span></div><StatusBadge tone={tone(item.status)}>{titleCase(item.status)}</StatusBadge></button>)}</div>
          ) : <EmptyState title="No optimizer executions" description="Applied multi-step plans will appear here." />}

          {selectedExecutionId && (
            <div className="execution-detail">
              {execution.loading ? <LoadingState label="Loading execution detail" /> : execution.error ? <ErrorState message={execution.error} retry={execution.reload} /> : execution.data ? <>
                <div className="plan-summary"><div><span>Status</span><strong>{titleCase(execution.data.status)}</strong></div><div><span>Risk cost</span><strong>{execution.data.baseline.student_risk_cost} → {execution.data.final.student_risk_cost}</strong></div><div><span>Clashes</span><strong>{execution.data.baseline.general_clashes} → {execution.data.final.general_clashes}</strong></div></div>
                {execution.data.steps?.length ? <div className="linked-steps">{execution.data.steps.map((step) => <span key={step.step_number}>Step {step.step_number} · change #{step.change_id}</span>)}</div> : null}
                <div className="button-row"><button className="btn btn--secondary" disabled={!canApplySelectedTerm || execution.data.status === 'undone' || Boolean(busy)} onClick={() => void rollback('undo')}><RotateCcw size={15}/>{busy === 'undo' ? 'Undoing…' : 'Undo execution'}</button><button className="btn btn--secondary" disabled={!canApplySelectedTerm || execution.data.status !== 'undone' || Boolean(busy)} onClick={() => void rollback('redo')}><RotateCw size={15}/>{busy === 'redo' ? 'Redoing…' : 'Redo execution'}</button></div>
              </> : null}
            </div>
          )}
        </Section>
      </div>
    </div>
  )
}

function timetableChangeSummary(change: TimetableChange) {
  if (change.change_type === 'manual_time_change') {
    return `${change.old_day} ${formatClock(change.old_start_time)}–${formatClock(change.old_end_time)} → ${change.new_day} ${formatClock(change.new_start_time)}–${formatClock(change.new_end_time)}`
  }
  return `${change.old_room || 'Unassigned'} → ${change.new_room || 'Unassigned'}`
}

function studentChangeSummary(change: StudentScheduleChange) {
  return `${change.old_day} ${formatClock(change.old_start_time)}–${formatClock(change.old_end_time)} → ${change.new_day} ${formatClock(change.new_start_time)}–${formatClock(change.new_end_time)}`
}

function auditState(item: AuditItem, side: 'before' | 'after') {
  const value = item[side]
  if (value.room !== undefined) return value.room || 'Unassigned'
  return `${value.day || 'Unknown day'} ${formatClock(value.start_time)}–${formatClock(value.end_time)}`
}

export function HistoryPage() {
  const changes = useAsync(() => historyApi.changes(), [])
  const studentChanges = useAsync(() => historyApi.studentChanges(), [])
  const audit = useAsync(() => historyApi.audit(), [])
  const [message, setMessage] = useState('')
  const [actionError, setActionError] = useState('')
  const [busy, setBusy] = useState('')

  async function act(kind: 'change' | 'student', mode: 'undo' | 'redo', id: number) {
    if (busy) return
    if (!window.confirm(`${mode === 'undo' ? 'Undo' : 'Redo'} ${kind === 'change' ? 'timetable' : 'student schedule'} change #${id}?`)) return
    setBusy(`${kind}-${mode}-${id}`)
    setMessage('')
    setActionError('')
    try {
      if (kind === 'change' && mode === 'undo') await historyApi.undoChange(id)
      else if (kind === 'change') await historyApi.redoChange(id)
      else if (mode === 'undo') await historyApi.undoStudentChange(id)
      else await historyApi.redoStudentChange(id)
      setMessage(`${kind === 'change' ? 'Timetable' : 'Student schedule'} change ${mode} completed.`)
      await Promise.all([changes.reload(), studentChanges.reload(), audit.reload()])
    } catch (error) {
      setActionError(operationError(error, `Unable to ${mode} change #${id}.`))
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="page">
      <PageHeader title="Change history & audit" description="Inspect every tracked schedule mutation and use contextual undo or redo controls." />
      {message && <SuccessNote>{message}</SuccessNote>}
      {actionError && <ErrorNote>{actionError}</ErrorNote>}
      <div className="metric-grid">
        <Metric label="Total changes" value={audit.data?.summary.total_changes ?? '—'} />
        <Metric label="Active" value={audit.data?.summary.active_changes ?? '—'} tone="success" />
        <Metric label="Undone" value={audit.data?.summary.undone_changes ?? '—'} tone="neutral" />
        <Metric label="Time changes" value={audit.data?.summary.timetable_time_changes ?? '—'} tone="warning" />
        <Metric label="Student schedule" value={audit.data?.summary.student_schedule_changes ?? '—'} tone="info" />
      </div>

      <Section title="Timetable changes" description="Room assignments and manual day/time edits." actions={<HistoryIcon size={18} />}>
        {changes.loading ? <LoadingState /> : changes.error ? <ErrorState message={changes.error} retry={changes.reload} /> : changes.data?.changes.length ? (
          <div className="table-wrap"><table className="data-table"><thead><tr><th>Change</th><th>Entry</th><th>Before → after</th><th>Reason</th><th>Status</th><th>Action</th></tr></thead><tbody>{changes.data.changes.map((change) => (
            <tr key={change.id}><td><strong>#{change.id}</strong><small>{titleCase(change.change_type)}</small></td><td>Entry #{change.entry_id}<small>{change.created_at ? formatRelative(change.created_at) : 'Time unavailable'}</small></td><td>{timetableChangeSummary(change)}</td><td>{change.reason || 'No reason recorded'}</td><td><StatusBadge tone={change.undone ? 'neutral' : 'success'}>{change.undone ? 'Undone' : 'Active'}</StatusBadge></td><td>{change.undone ? <button className="btn btn--secondary" disabled={Boolean(busy)} onClick={() => void act('change', 'redo', change.id)}><RotateCw size={15}/>{busy === `change-redo-${change.id}` ? 'Redoing…' : 'Redo'}</button> : <button className="btn btn--secondary" disabled={Boolean(busy)} onClick={() => void act('change', 'undo', change.id)}><RotateCcw size={15}/>{busy === `change-undo-${change.id}` ? 'Undoing…' : 'Undo'}</button>}</td></tr>
          ))}</tbody></table></div>
        ) : <EmptyState title="No timetable changes" description="Applied room or time changes will appear here." />}
      </Section>

      <Section title="Student schedule changes" description="Optimizer and conflict-group changes tracked with before/after risk impact.">
        {studentChanges.loading ? <LoadingState /> : studentChanges.error ? <ErrorState message={studentChanges.error} retry={studentChanges.reload} /> : studentChanges.data?.changes.length ? (
          <div className="table-wrap"><table className="data-table"><thead><tr><th>Change</th><th>Group / entry</th><th>Before → after</th><th>Risk impact</th><th>Status</th><th>Action</th></tr></thead><tbody>{studentChanges.data.changes.map((change) => (
            <tr key={change.id}><td><strong>#{change.id}</strong><small>{titleCase(change.change_type)}</small></td><td>{change.report_id ? `Report #${change.report_id}` : change.group_id ? `Group #${change.group_id}` : 'Direct resolution'}<small>Entry #{change.entry_id}</small></td><td>{studentChangeSummary(change)}</td><td><strong>{change.risk_cost_before} → {change.risk_cost_after}</strong><small>{change.total_risks_before} → {change.total_risks_after} signals</small></td><td><StatusBadge tone={change.undone ? 'neutral' : 'success'}>{change.undone ? 'Undone' : 'Active'}</StatusBadge></td><td>{change.undone ? <button className="btn btn--secondary" disabled={Boolean(busy)} onClick={() => void act('student', 'redo', change.id)}><RotateCw size={15}/>{busy === `student-redo-${change.id}` ? 'Redoing…' : 'Redo'}</button> : <button className="btn btn--secondary" disabled={Boolean(busy)} onClick={() => void act('student', 'undo', change.id)}><RotateCcw size={15}/>{busy === `student-undo-${change.id}` ? 'Undoing…' : 'Undo'}</button>}</td></tr>
          ))}</tbody></table></div>
        ) : <EmptyState title="No student schedule changes" description="Applied optimizer or conflict-group changes will appear here." />}
      </Section>

      <Section title="Unified audit trail" description="A chronological view across timetable and student-schedule history.">
        {audit.loading ? <LoadingState /> : audit.error ? <ErrorState message={audit.error} retry={audit.reload} /> : audit.data?.audit_trail.length ? (
          <div className="table-wrap"><table className="data-table"><thead><tr><th>When</th><th>Type</th><th>Class</th><th>Before → after</th><th>Status</th></tr></thead><tbody>{audit.data.audit_trail.map((item) => (
            <tr key={`${item.audit_type}-${item.history_id}`}><td>{item.created_at ? formatRelative(item.created_at) : 'Time unavailable'}</td><td><strong>{titleCase(item.audit_type)}</strong><small>History #{item.history_id}</small></td><td>{item.course_code || item.course_name || `Entry #${item.entry_id}`}</td><td>{auditState(item, 'before')} → {auditState(item, 'after')}</td><td><StatusBadge tone={item.undone ? 'neutral' : 'success'}>{item.undone ? 'Undone' : 'Active'}</StatusBadge></td></tr>
          ))}</tbody></table></div>
        ) : <EmptyState title="Audit trail is empty" description="Tracked timetable mutations will be recorded here." />}
      </Section>
    </div>
  )
}
