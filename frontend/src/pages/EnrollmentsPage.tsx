import { Plus, Trash2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { studentApi } from '../api/student'
import { ApiError } from '../api/client'
import { Field, Input } from '../components/Form'
import { EmptyState, ErrorNote, ErrorState, LoadingState, PageHeader, Section, SuccessNote } from '../components/Ui'
import { useAsync } from '../hooks/useAsync'
import { formatRelative } from '../utils/format'

export function EnrollmentsPage() {
  const enrollments = useAsync(() => studentApi.enrollments(), [])
  const [courseCode, setCourseCode] = useState(''); const [section, setSection] = useState(''); const [semester, setSemester] = useState('')
  const [busy, setBusy] = useState(false); const [message, setMessage] = useState(''); const [error, setError] = useState('')
  const [removingId, setRemovingId] = useState<number | null>(null)

  async function add(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('')
    try { const payload = { course_code: courseCode, section, semester }; const preview = await studentApi.validateEnrollment(payload); if (preview.has_conflicts) { const conflicts = preview.conflicts.map((item) => `${item.proposed_class.course_code || courseCode} overlaps ${item.conflicts_with.course_code || item.conflicts_with.course_name} on ${item.day} ${item.overlap_start}–${item.overlap_end}`).join('\n'); const alternatives = preview.alternate_sections.filter((item) => item.conflict_free).map((item) => item.section); const alternativeNote = alternatives.length ? `\nTimetable-only conflict-free section(s): ${alternatives.join(', ')}. Capacity and eligibility are not verified.` : ''; if (!window.confirm(`${conflicts}${alternativeNote}\n\nAdd this enrollment anyway?`)) return } const created = await studentApi.addEnrollment(payload); setCourseCode(''); setSection(''); setSemester(''); setMessage(created.conflict_validation.has_conflicts ? 'Enrollment added with a verified timetable conflict. Review your personal timetable and submit a clash report if institutional action is required.' : 'Enrollment added. Your personal timetable has no detected conflict from this mapping.'); await enrollments.reload() }
    catch (err) { setError(err instanceof ApiError ? err.message : 'Unable to add enrollment.') }
    finally { setBusy(false) }
  }

  async function remove(id: number) { if (!window.confirm('Remove this enrollment from your personal schedule?')) return; setRemovingId(id); setError(''); setMessage(''); try { await studentApi.removeEnrollment(id); setMessage('Enrollment removed from your personal schedule.'); await enrollments.reload() } catch (err) { setError(err instanceof ApiError ? err.message : 'Unable to remove enrollment.') } finally { setRemovingId(null) } }

  return <div className="page"><PageHeader title="Enrollments" description="Your stable course, section and semester mappings determine the classes shown in your personal timetable."/>
    <div className="two-column two-column--narrow"><Section title="Add enrollment" description="Course and section matching is normalized by the backend."><form className="form-stack" onSubmit={add}><Field label="Course code"><Input value={courseCode} onChange={(e) => setCourseCode(e.target.value)} placeholder="AI232" maxLength={50} required/></Field><div className="form-row"><Field label="Section"><Input value={section} onChange={(e) => setSection(e.target.value)} placeholder="A" maxLength={50} required/></Field><Field label="Semester"><Input value={semester} onChange={(e) => setSemester(e.target.value)} placeholder="Fall 2026" maxLength={50} required/></Field></div>{error && <ErrorNote>{error}</ErrorNote>}{message && <SuccessNote>{message}</SuccessNote>}<button className="btn btn--primary" disabled={busy || removingId !== null}><Plus size={16}/>{busy ? 'Adding…' : 'Add enrollment'}</button></form></Section>
      <Section title="Current enrollments" description="Removing an enrollment only changes your mapping; it does not alter the institutional timetable.">{enrollments.loading ? <LoadingState/> : enrollments.error ? <ErrorState message={enrollments.error} retry={enrollments.reload}/> : enrollments.data?.length ? <div className="enrollment-list">{enrollments.data.map((item) => <article key={item.id}><div className="course-token">{item.course_code.slice(0, 2)}</div><div><strong>{item.course_code}</strong><span>Section {item.section} · {item.semester}</span><small>Added {formatRelative(item.created_at)}</small></div><button className="icon-btn icon-btn--danger" disabled={removingId !== null} onClick={() => void remove(item.id)} aria-label={`Remove ${item.course_code}`}><Trash2 size={17}/></button></article>)}</div> : <EmptyState title="No enrollments yet" description="Add your first course mapping to build your personal timetable."/>}</Section></div>
  </div>
}
