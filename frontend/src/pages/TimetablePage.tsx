import { Clock3, FileUp, PencilLine, Plus, Search, Trash2 } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { facultyApi } from '../api/faculty'
import { studentApi } from '../api/student'
import { termsApi } from '../api/terms'
import { timetableApi, type TimetableCreatePayload } from '../api/timetable'
import { ApiError } from '../api/client'
import { Field, Input, Select } from '../components/Form'
import { TimetableView } from '../components/TimetableView'
import { EmptyState, ErrorNote, ErrorState, LoadingState, Modal, PageHeader, Section, SuccessNote } from '../components/Ui'
import { useAuth } from '../features/auth/AuthContext'
import { useAsync } from '../hooks/useAsync'
import { classLabel, formatClock, titleCase } from '../utils/format'
import type { ClassType, DayName, TimetableEntry } from '../types/api'

const days: DayName[] = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
const classTypes: ClassType[] = ['lecture','lab','tutorial','online','hybrid','other']

export function TimetablePage() {
  const { user } = useAuth()
  const manager = Boolean(user && ['coordinator','admin'].includes(user.role))
  const termAware = Boolean(user && ['faculty','coordinator','admin'].includes(user.role))
  const terms = useAsync(() => termAware ? termsApi.list() : Promise.resolve({ terms: [], total: 0, active_term_id: null }), [termAware])
  const [selectedTermId, setSelectedTermId] = useState<number | null>(null)
  const effectiveTermId = selectedTermId ?? terms.data?.active_term_id ?? terms.data?.terms.find((term) => term.status === 'planning')?.id ?? terms.data?.terms[0]?.id ?? null
  const selectedTerm = terms.data?.terms.find((term) => term.id === effectiveTermId) ?? null
  const canManageSelectedTerm = Boolean(manager && selectedTerm && selectedTerm.status !== 'archived')
  const source = useAsync(
    () => user?.role === 'student'
      ? studentApi.timetable()
      : termAware && terms.loading
        ? Promise.resolve([] as TimetableEntry[])
        : user?.role === 'faculty'
          ? facultyApi.timetable(effectiveTermId)
          : timetableApi.list(effectiveTermId),
    [user?.role, termAware, terms.loading, effectiveTermId],
  )
  const freeSlots = useAsync(
    () => user?.role === 'faculty'
      ? terms.loading
        ? Promise.resolve(null)
        : facultyApi.freeSlots(effectiveTermId)
      : Promise.resolve(null),
    [user?.role, terms.loading, effectiveTermId],
  )
  const [query, setQuery] = useState(''); const [view, setView] = useState<'week'|'list'>('week'); const [createOpen, setCreateOpen] = useState(false); const [roomEntry, setRoomEntry] = useState<TimetableEntry | null>(null); const [timeEntry, setTimeEntry] = useState<TimetableEntry | null>(null); const [message, setMessage] = useState(''); const [actionError, setActionError] = useState(''); const [deletingId, setDeletingId] = useState<number | null>(null); const [importing, setImporting] = useState(false)
  const filtered = useMemo(() => (source.data || []).filter((entry) => [entry.course_code, entry.course_name, entry.faculty, entry.room, entry.section].some((value) => value?.toLowerCase().includes(query.toLowerCase()))), [source.data, query])
  async function remove(id: number) { if (!window.confirm('Delete this timetable entry? This changes the institutional timetable.')) return; setDeletingId(id); setMessage(''); setActionError(''); try { await timetableApi.remove(id); setMessage('Timetable entry deleted.'); await source.reload() } catch (err) { setActionError(err instanceof ApiError ? err.message : 'Unable to delete the timetable entry.') } finally { setDeletingId(null) } }
  async function upload(file: File | undefined) { if (!file || importing) return; setImporting(true); setMessage(''); setActionError(''); try { await timetableApi.importFile(file, effectiveTermId); setMessage('Timetable import completed.'); await source.reload() } catch (err) { setActionError(err instanceof ApiError ? err.message : 'Import failed.') } finally { setImporting(false) } }

  return <div className="page"><PageHeader title={user?.role === 'student' ? 'My timetable' : user?.role === 'faculty' ? 'Teaching timetable' : 'Timetable management'} description={manager ? 'Manage the institutional timetable, imports and room assignments.' : 'Your schedule is derived from the assignments mapped to your account.'} actions={<div className="button-row"><button className={`btn btn--ghost ${view === 'week' ? 'is-active' : ''}`} onClick={() => setView('week')}>Week</button><button className={`btn btn--ghost ${view === 'list' ? 'is-active' : ''}`} onClick={() => setView('list')}>List</button>{canManageSelectedTerm && <button className="btn btn--primary" onClick={() => setCreateOpen(true)}><Plus size={16}/>New entry</button>}</div>}/>
    {message && <SuccessNote>{message}</SuccessNote>}
    {actionError && <ErrorNote>{actionError}</ErrorNote>}
    {termAware && <div className="toolbar"><Select aria-label="Academic term" value={effectiveTermId ? String(effectiveTermId) : ''} onChange={(e) => setSelectedTermId(Number(e.target.value))} disabled={terms.loading || !terms.data?.terms.length}><option value="" disabled>{terms.loading ? 'Loading terms…' : 'Select term'}</option>{terms.data?.terms.map((term) => <option key={term.id} value={term.id}>{term.name} - {term.status}</option>)}</Select>{selectedTerm && <span className="muted">{selectedTerm.code} - {selectedTerm.status}{selectedTerm.status === 'archived' ? ' - read-only' : ''}</span>}</div>}
    {termAware && terms.error && <ErrorNote>{terms.error}</ErrorNote>}
    {user?.role === 'faculty' && <Section title="Open timetable windows">{freeSlots.loading ? <LoadingState label="Loading open windows"/> : freeSlots.error ? <ErrorState message={freeSlots.error} retry={freeSlots.reload}/> : freeSlots.data ? <><p className="muted">{freeSlots.data.note}</p>{freeSlots.data.slots.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Day</th><th>Open time</th><th>Duration</th></tr></thead><tbody>{freeSlots.data.slots.map((slot) => <tr key={`${slot.day}-${slot.start_time}-${slot.end_time}`}><td><strong>{slot.day}</strong></td><td>{formatClock(slot.start_time)} - {formatClock(slot.end_time)}</td><td>{slot.duration_minutes} min</td></tr>)}</tbody></table></div> : <EmptyState title="No open timetable windows" description="No institutional timetable gap meets the minimum duration for this term."/>}</> : null}</Section>}
    <div className="toolbar"><label className="search-box"><Search size={17}/><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search course, room, faculty or section"/></label>{canManageSelectedTerm && <label className={`btn btn--secondary file-button ${importing ? 'is-disabled' : ''}`} aria-disabled={importing}><FileUp size={16}/>{importing ? 'Importing…' : 'Import CSV/XLSX'}<input type="file" accept=".csv,.xlsx" disabled={importing} onChange={(e) => { void upload(e.target.files?.[0]); e.currentTarget.value = '' }}/></label>}</div>
    {source.loading ? <LoadingState label="Loading timetable"/> : source.error ? <ErrorState message={source.error} retry={source.reload}/> : filtered.length ? view === 'week' ? <TimetableView entries={filtered}/> : <Section><div className="table-wrap"><table className="data-table"><thead><tr><th>Course</th><th>Day / Time</th><th>Section</th><th>Faculty</th><th>Room</th><th>Type</th>{canManageSelectedTerm && <th>Actions</th>}</tr></thead><tbody>{filtered.map((entry) => <tr key={entry.id}><td><strong>{classLabel(entry)}</strong><small>{entry.course_code || 'Special event'}</small></td><td>{entry.day}<small>{formatClock(entry.start_time)} – {formatClock(entry.end_time)}</small></td><td>{entry.section || 'Shared'}</td><td>{entry.faculty || '—'}</td><td>{entry.room || 'TBA'}</td><td>{titleCase(entry.class_type)}</td>{canManageSelectedTerm && <td><div className="row-actions"><button className="icon-btn" disabled={deletingId !== null} onClick={() => setRoomEntry(entry)} aria-label="Change room"><PencilLine size={16}/></button><button className="icon-btn" disabled={deletingId !== null} onClick={() => setTimeEntry(entry)} aria-label="Change day and time"><Clock3 size={16}/></button><button className="icon-btn icon-btn--danger" disabled={deletingId !== null} onClick={() => void remove(entry.id)} aria-label="Delete entry"><Trash2 size={16}/></button></div></td>}</tr>)}</tbody></table></div></Section> : <EmptyState title="No timetable entries found" description={query ? 'Try a broader search.' : 'No schedule entries are available for this view.'}/>}
    {createOpen && <CreateTimetableModal termId={effectiveTermId} onClose={() => setCreateOpen(false)} onCreated={async () => { setCreateOpen(false); setActionError(''); setMessage('Timetable entry created.'); await source.reload() }}/>}
    {roomEntry && <RoomModal entry={roomEntry} onClose={() => setRoomEntry(null)} onSaved={async () => { setRoomEntry(null); setActionError(''); setMessage('Room updated.'); await source.reload() }}/>}
    {timeEntry && <TimeModal entry={timeEntry} onClose={() => setTimeEntry(null)} onSaved={async () => { setTimeEntry(null); setActionError(''); setMessage('Timetable day and time updated safely.'); await source.reload() }}/>}
  </div>
}

function CreateTimetableModal({ termId, onClose, onCreated }: { termId: number | null; onClose: () => void; onCreated: () => Promise<void> }) {
  const [form, setForm] = useState<TimetableCreatePayload>({ day: 'Monday', start_time: '09:00', end_time: '10:00', class_type: 'lecture', source: 'manual' }); const [error, setError] = useState(''); const [busy, setBusy] = useState(false)
  const set = (key: keyof TimetableCreatePayload, value: string) => setForm((current) => ({ ...current, [key]: value || null }))
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setError(''); try { await timetableApi.create(form, termId); await onCreated() } catch (err) { setError(err instanceof ApiError ? err.message : 'Unable to create entry.') } finally { setBusy(false) } }
  return <Modal title="Create timetable entry" onClose={onClose} wide><form className="form-grid" onSubmit={submit}><Field label="Course code"><Input onChange={(e) => set('course_code', e.target.value)} placeholder="CS210"/></Field><Field label="Course name"><Input onChange={(e) => set('course_name', e.target.value)} placeholder="Data Structures"/></Field><Field label="Section"><Input onChange={(e) => set('section', e.target.value)} placeholder="A"/></Field><Field label="Semester"><Input onChange={(e) => set('semester', e.target.value)} placeholder="Fall 2026"/></Field><Field label="Faculty"><Input onChange={(e) => set('faculty', e.target.value)} placeholder="Dr. Ahmed"/></Field><Field label="Room"><Input onChange={(e) => set('room', e.target.value)} placeholder="CS-301"/></Field><Field label="Day"><Select value={form.day} onChange={(e) => setForm((f) => ({ ...f, day: e.target.value as DayName }))}>{days.map((day) => <option key={day}>{day}</option>)}</Select></Field><Field label="Class type"><Select value={form.class_type} onChange={(e) => setForm((f) => ({ ...f, class_type: e.target.value as ClassType }))}>{classTypes.map((type) => <option key={type}>{type}</option>)}</Select></Field><Field label="Start time"><Input type="time" value={form.start_time} onChange={(e) => setForm((f) => ({ ...f, start_time: e.target.value }))} required/></Field><Field label="End time"><Input type="time" value={form.end_time} onChange={(e) => setForm((f) => ({ ...f, end_time: e.target.value }))} required/></Field>{error && <div className="form-error form-grid__full">{error}</div>}<div className="modal-actions form-grid__full"><button type="button" className="btn btn--secondary" onClick={onClose}>Cancel</button><button className="btn btn--primary" disabled={busy}>{busy ? 'Creating…' : 'Create entry'}</button></div></form></Modal>
}

function RoomModal({ entry, onClose, onSaved }: { entry: TimetableEntry; onClose: () => void; onSaved: () => Promise<void> }) {
  const [room, setRoom] = useState(entry.room || ''); const [busy, setBusy] = useState(false); const [error, setError] = useState('')
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setError(''); try { await timetableApi.changeRoom(entry.id, room); await onSaved() } catch (err) { setError(err instanceof ApiError ? err.message : 'Unable to change room.') } finally { setBusy(false) } }
  return <Modal title={`Change room · ${entry.course_code || entry.id}`} onClose={onClose}><form className="form-stack" onSubmit={submit}><Field label="Room"><Input value={room} onChange={(e) => setRoom(e.target.value)} required/></Field>{error && <div className="form-error">{error}</div>}<div className="modal-actions"><button type="button" className="btn btn--secondary" onClick={onClose}>Cancel</button><button className="btn btn--primary" disabled={busy}>Save room</button></div></form></Modal>
}

function TimeModal({ entry, onClose, onSaved }: { entry: TimetableEntry; onClose: () => void; onSaved: () => Promise<void> }) {
  const [day, setDay] = useState<DayName>(entry.day); const [startTime, setStartTime] = useState(entry.start_time); const [endTime, setEndTime] = useState(entry.end_time); const [busy, setBusy] = useState(false); const [error, setError] = useState('')
  async function submit(event: FormEvent) { event.preventDefault(); if (busy) return; setBusy(true); setError(''); try { await timetableApi.changeTime(entry.id, { day, start_time: startTime, end_time: endTime }); await onSaved() } catch (err) { setError(err instanceof ApiError ? err.message : 'Unable to change the timetable time.') } finally { setBusy(false) } }
  return <Modal title={`Change day and time · ${entry.course_code || entry.id}`} onClose={onClose}><form className="form-stack" onSubmit={submit}><Field label="Day"><Select value={day} onChange={(e) => setDay(e.target.value as DayName)}>{days.map((item) => <option key={item}>{item}</option>)}</Select></Field><div className="form-row"><Field label="Start time"><Input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} required/></Field><Field label="End time"><Input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} required/></Field></div><p className="muted">The backend rejects faculty, room, structural, or increased student-risk conflicts and records this change for undo/redo.</p>{error && <ErrorNote>{error}</ErrorNote>}<div className="modal-actions"><button type="button" className="btn btn--secondary" disabled={busy} onClick={onClose}>Cancel</button><button className="btn btn--primary" disabled={busy}>{busy ? 'Validating…' : 'Save day and time'}</button></div></form></Modal>
}
