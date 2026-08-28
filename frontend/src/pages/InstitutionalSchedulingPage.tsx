import { Plus, Trash2, WandSparkles } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { institutionalSchedulingApi } from '../api/institutionalScheduling'
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
  FacultyAvailabilityDay,
  FacultyDesignation,
  TimetableGenerationPreview,
} from '../types/api'

const weekdays: FacultyAvailabilityDay[] = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
]

export function InstitutionalSchedulingPage() {
  const terms = useAsync(() => termsApi.list(), [])
  const [selectedTermId, setSelectedTermId] = useState<number | null>(null)
  const defaultTermId =
    terms.data?.terms.find((term) => term.status === 'planning')?.id ??
    terms.data?.active_term_id ??
    terms.data?.terms[0]?.id ??
    null
  const effectiveTermId = selectedTermId ?? defaultTermId
  const selectedTerm =
    terms.data?.terms.find((term) => term.id === effectiveTermId) ?? null
  const writable = selectedTerm?.status === 'planning'

  const offerings = useAsync(
    () =>
      effectiveTermId
        ? institutionalSchedulingApi.courseOfferings(effectiveTermId)
        : Promise.resolve([]),
    [effectiveTermId],
  )
  const workloads = useAsync(
    () =>
      effectiveTermId
        ? institutionalSchedulingApi.workloads(effectiveTermId)
        : Promise.resolve([]),
    [effectiveTermId],
  )

  const [facultyId, setFacultyId] = useState('')
  const selectedWorkload = workloads.data?.find(
    (item) => item.faculty_user_id === Number(facultyId),
  )
  const availability = useAsync(
    () =>
      effectiveTermId && Number(facultyId)
        ? institutionalSchedulingApi.managedAvailability(
            Number(facultyId),
            effectiveTermId,
          )
        : Promise.resolve([]),
    [effectiveTermId, facultyId],
  )

  const [courseCode, setCourseCode] = useState('')
  const [courseName, setCourseName] = useState('')
  const [semester, setSemester] = useState('1')
  const [section, setSection] = useState('A')
  const [classType, setClassType] = useState<'lecture' | 'lab'>('lecture')
  const [duration, setDuration] = useState('60')
  const [room, setRoom] = useState('')

  const [designationDraft, setDesignationDraft] =
    useState<FacultyDesignation | ''>('')
  const [availabilityDay, setAvailabilityDay] =
    useState<FacultyAvailabilityDay>('Monday')
  const [availabilityStart, setAvailabilityStart] = useState('08:00')
  const [availabilityEnd, setAvailabilityEnd] = useState('12:00')

  const [preview, setPreview] = useState<TimetableGenerationPreview | null>(null)
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const facultyDesignation =
    designationDraft || selectedWorkload?.designation || ''

  const summary = useMemo(
    () => ({
      offerings: offerings.data?.length ?? 0,
      configuredFaculty:
        workloads.data?.filter((item) => item.profile_configured).length ?? 0,
      facultyCount: workloads.data?.length ?? 0,
    }),
    [offerings.data, workloads.data],
  )

  function resetFeedback() {
    setMessage('')
    setError('')
  }

  function invalidatePreview() {
    setPreview(null)
  }

  function changeTerm(value: string) {
    setSelectedTermId(Number(value))
    setFacultyId('')
    setDesignationDraft('')
    setPreview(null)
    resetFeedback()
  }

  async function createOffering(event: FormEvent) {
    event.preventDefault()
    if (!effectiveTermId || !writable || busy) return
    setBusy('offering')
    resetFeedback()
    try {
      await institutionalSchedulingApi.createCourseOffering({
        term_id: effectiveTermId,
        course_code: courseCode,
        course_name: courseName,
        semester: Number(semester),
        section,
        class_type: classType,
        duration_minutes: Number(duration),
        room,
      })
      setMessage('Course offering created.')
      setCourseCode('')
      setCourseName('')
      setSection('A')
      setRoom('')
      invalidatePreview()
      await Promise.all([offerings.reload(), workloads.reload()])
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Unable to create offering.',
      )
    } finally {
      setBusy('')
    }
  }

  async function removeOffering(id: number) {
    if (!window.confirm('Delete this course offering?')) return
    setBusy(`offering-${id}`)
    resetFeedback()
    try {
      await institutionalSchedulingApi.deleteCourseOffering(id)
      setMessage('Course offering deleted.')
      invalidatePreview()
      await offerings.reload()
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Unable to delete offering.',
      )
    } finally {
      setBusy('')
    }
  }

  async function saveDesignation() {
    if (
      !effectiveTermId ||
      !Number(facultyId) ||
      !facultyDesignation ||
      !writable ||
      busy
    ) {
      return
    }
    setBusy('designation')
    resetFeedback()
    try {
      await institutionalSchedulingApi.setDesignation(
        Number(facultyId),
        facultyDesignation,
        effectiveTermId,
      )
      setMessage('Faculty teaching designation saved.')
      setDesignationDraft('')
      invalidatePreview()
      await workloads.reload()
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'Unable to save teaching designation.',
      )
    } finally {
      setBusy('')
    }
  }

  async function addAvailability(event: FormEvent) {
    event.preventDefault()
    if (!effectiveTermId || !Number(facultyId) || !writable || busy) return
    setBusy('availability')
    resetFeedback()
    try {
      await institutionalSchedulingApi.addManagedAvailability({
        faculty_user_id: Number(facultyId),
        term_id: effectiveTermId,
        day: availabilityDay,
        start_time: availabilityStart,
        end_time: availabilityEnd,
      })
      setMessage('Faculty availability added.')
      invalidatePreview()
      await availability.reload()
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Unable to add availability.',
      )
    } finally {
      setBusy('')
    }
  }

  async function removeAvailability(id: number) {
    if (!window.confirm('Delete this faculty availability window?')) return
    setBusy(`availability-${id}`)
    resetFeedback()
    try {
      await institutionalSchedulingApi.deleteManagedAvailability(id)
      setMessage('Faculty availability removed.')
      invalidatePreview()
      await availability.reload()
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'Unable to remove availability.',
      )
    } finally {
      setBusy('')
    }
  }

  async function generatePreview() {
    if (!effectiveTermId || !writable || busy) return
    setBusy('preview')
    resetFeedback()
    try {
      const result =
        await institutionalSchedulingApi.previewGeneration(effectiveTermId)
      setPreview(result)
      setMessage('Timetable generation preview refreshed.')
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'Unable to preview timetable generation.',
      )
    } finally {
      setBusy('')
    }
  }

  async function applyPreview() {
    if (
      !effectiveTermId ||
      !preview ||
      preview.status !== 'READY' ||
      !preview.complete ||
      !writable ||
      busy
    ) {
      return
    }
    if (
      !window.confirm(
        `Apply this verified preview and create ${preview.proposed_count} timetable session(s)?`,
      )
    ) {
      return
    }
    setBusy('apply')
    resetFeedback()
    try {
      const result = await institutionalSchedulingApi.applyGeneration(
        effectiveTermId,
        preview.preview_id,
      )
      setMessage(result.message)
      setPreview(null)
      await offerings.reload()
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'Unable to apply timetable generation.',
      )
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="page">
      <PageHeader
        title="Institutional scheduling"
        description="Prepare structured offerings, faculty workload and true availability, then preview and apply the deterministic timetable."
        actions={
          <div className="row-actions">
            <a className="btn btn--secondary" href="/faculty-assignments">
              Faculty allocations
            </a>
            <a className="btn btn--secondary" href="/timetable">
              Timetable
            </a>
            <a className="btn btn--secondary" href="/insights">
              Quality
            </a>
          </div>
        }
      />

      {message && <SuccessNote>{message}</SuccessNote>}
      {error && <ErrorNote>{error}</ErrorNote>}
      {terms.error && <ErrorNote>{terms.error}</ErrorNote>}

      <div className="toolbar">
        <Select
          aria-label="Academic term"
          value={effectiveTermId ? String(effectiveTermId) : ''}
          onChange={(event) => changeTerm(event.target.value)}
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
          <StatusBadge tone={writable ? 'warning' : 'neutral'}>
            {selectedTerm.code} - {selectedTerm.status}
          </StatusBadge>
        )}
      </div>

      {selectedTerm && !writable && (
        <ErrorNote>
          Structured scheduling changes and timetable generation are available
          only while a term is in planning. This term remains readable here.
        </ErrorNote>
      )}

      <div className="metrics-grid">
        <Metric
          label="Offerings"
          value={summary.offerings}
          hint="Lecture/lab components in this term"
        />
        <Metric
          label="Faculty profiles"
          value={`${summary.configuredFaculty}/${summary.facultyCount}`}
          hint="Active faculty with designation configured"
        />
        <Metric
          label="Preview state"
          value={preview?.status ?? 'Not run'}
          hint={
            preview
              ? `${preview.proposed_count} proposed session(s)`
              : 'Run after readiness setup'
          }
        />
      </div>

      {writable && (
        <Section
          title="Add course offering"
          description="Define the real lecture/lab components that faculty can be allocated to."
        >
          <form className="form-grid" onSubmit={createOffering}>
            <Field label="Course code">
              <Input
                value={courseCode}
                onChange={(event) => setCourseCode(event.target.value)}
                maxLength={50}
                required
              />
            </Field>
            <Field label="Course name">
              <Input
                value={courseName}
                onChange={(event) => setCourseName(event.target.value)}
                maxLength={150}
                required
              />
            </Field>
            <Field label="Semester">
              <Select
                value={semester}
                onChange={(event) => setSemester(event.target.value)}
              >
                {Array.from({ length: 8 }, (_, index) => index + 1).map(
                  (value) => (
                    <option value={value} key={value}>
                      Semester {value}
                    </option>
                  ),
                )}
              </Select>
            </Field>
            <Field label="Section">
              <Input
                value={section}
                onChange={(event) => setSection(event.target.value)}
                maxLength={50}
                required
              />
            </Field>
            <Field label="Class type">
              <Select
                value={classType}
                onChange={(event) =>
                  setClassType(event.target.value as 'lecture' | 'lab')
                }
              >
                <option value="lecture">Lecture</option>
                <option value="lab">Lab</option>
              </Select>
            </Field>
            <Field label="Duration minutes">
              <Input
                type="number"
                min={30}
                max={240}
                value={duration}
                onChange={(event) => setDuration(event.target.value)}
                required
              />
            </Field>
            <Field
              label="Room/location"
              hint="Required by the deterministic generator; use an explicit online location when applicable."
            >
              <Input
                value={room}
                onChange={(event) => setRoom(event.target.value)}
                maxLength={150}
                required
              />
            </Field>
            <div className="form-grid__full">
              <button
                className="btn btn--primary"
                disabled={Boolean(busy)}
              >
                <Plus size={16} />
                {busy === 'offering' ? 'Adding…' : 'Add offering'}
              </button>
            </div>
          </form>
        </Section>
      )}

      <Section
        title="Course offerings"
        description="The structured source of truth for planning-term allocation and generation."
      >
        {offerings.loading ? (
          <LoadingState label="Loading offerings" />
        ) : offerings.error ? (
          <ErrorState message={offerings.error} retry={offerings.reload} />
        ) : offerings.data?.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Course</th>
                  <th>Semester</th>
                  <th>Section</th>
                  <th>Type</th>
                  <th>Duration</th>
                  <th>Room</th>
                  {writable && <th>Action</th>}
                </tr>
              </thead>
              <tbody>
                {offerings.data.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <strong>{item.course_code}</strong>
                      <small>{item.course_name}</small>
                    </td>
                    <td>{item.semester}</td>
                    <td>{item.section}</td>
                    <td>{item.class_type}</td>
                    <td>{item.duration_minutes} min</td>
                    <td>{item.room || 'Not set'}</td>
                    {writable && (
                      <td>
                        <button
                          className="icon-btn icon-btn--danger"
                          aria-label={`Delete offering ${item.course_code} ${item.class_type}`}
                          disabled={Boolean(busy)}
                          onClick={() => void removeOffering(item.id)}
                        >
                          <Trash2 size={16} />
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No course offerings"
            description="Create lecture/lab offerings before allocating faculty or generating a timetable."
          />
        )}
      </Section>

      <Section
        title="Faculty readiness"
        description="Configure designation-backed workload and true availability used by hard scheduling constraints."
      >
        {workloads.loading ? (
          <LoadingState label="Loading faculty workload" />
        ) : workloads.error ? (
          <ErrorState message={workloads.error} retry={workloads.reload} />
        ) : (
          <>
            <div className="form-grid">
              <Field label="Faculty member">
                <Select
                  value={facultyId}
                  onChange={(event) => {
                    setFacultyId(event.target.value)
                    setDesignationDraft('')
                    invalidatePreview()
                  }}
                >
                  <option value="">Select faculty</option>
                  {workloads.data?.map((item) => (
                    <option
                      key={item.faculty_user_id}
                      value={item.faculty_user_id}
                    >
                      {item.faculty_name} · {item.faculty_email}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field
                label="Teaching designation"
                hint="Lecturer: 4 distinct subjects. Assistant Professor: 2."
              >
                <Select
                  value={facultyDesignation}
                  onChange={(event) =>
                    setDesignationDraft(
                      event.target.value as FacultyDesignation | '',
                    )
                  }
                  disabled={!facultyId || !writable}
                >
                  <option value="">Not configured</option>
                  <option value="lecturer">Lecturer</option>
                  <option value="assistant_professor">
                    Assistant Professor
                  </option>
                </Select>
              </Field>
              {writable && (
                <div className="form-grid__full">
                  <button
                    className="btn btn--secondary"
                    type="button"
                    onClick={() => void saveDesignation()}
                    disabled={
                      Boolean(busy) || !facultyId || !facultyDesignation
                    }
                  >
                    {busy === 'designation'
                      ? 'Saving…'
                      : 'Save designation'}
                  </button>
                </div>
              )}
            </div>

            {selectedWorkload && (
              <div className="metrics-grid">
                <Metric
                  label="Assigned subjects"
                  value={selectedWorkload.distinct_subjects_assigned}
                  hint={
                    selectedWorkload.subject_codes.join(', ') ||
                    'No subjects allocated'
                  }
                />
                <Metric
                  label="Maximum"
                  value={selectedWorkload.maximum_subjects ?? '—'}
                  hint={selectedWorkload.designation || 'Set designation first'}
                />
                <Metric
                  label="Remaining"
                  value={selectedWorkload.remaining_capacity ?? '—'}
                  hint="Distinct-subject capacity"
                />
              </div>
            )}

            {facultyId && (
              <>
                {writable && (
                  <form className="form-grid" onSubmit={addAvailability}>
                    <Field label="Availability day">
                      <Select
                        value={availabilityDay}
                        onChange={(event) =>
                          setAvailabilityDay(
                            event.target.value as FacultyAvailabilityDay,
                          )
                        }
                      >
                        {weekdays.map((day) => (
                          <option key={day} value={day}>
                            {day}
                          </option>
                        ))}
                      </Select>
                    </Field>
                    <Field label="Available from">
                      <Input
                        type="time"
                        value={availabilityStart}
                        onChange={(event) =>
                          setAvailabilityStart(event.target.value)
                        }
                        required
                      />
                    </Field>
                    <Field label="Available until">
                      <Input
                        type="time"
                        value={availabilityEnd}
                        onChange={(event) =>
                          setAvailabilityEnd(event.target.value)
                        }
                        required
                      />
                    </Field>
                    <div className="form-grid__full">
                      <button
                        className="btn btn--secondary"
                        disabled={Boolean(busy)}
                      >
                        <Plus size={16} />
                        {busy === 'availability'
                          ? 'Adding…'
                          : 'Add availability'}
                      </button>
                    </div>
                  </form>
                )}

                {availability.loading ? (
                  <LoadingState label="Loading availability" />
                ) : availability.error ? (
                  <ErrorState
                    message={availability.error}
                    retry={availability.reload}
                  />
                ) : availability.data?.length ? (
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Day</th>
                          <th>From</th>
                          <th>Until</th>
                          {writable && <th>Action</th>}
                        </tr>
                      </thead>
                      <tbody>
                        {availability.data.map((window) => (
                          <tr key={window.id}>
                            <td>{window.day}</td>
                            <td>{window.start_time}</td>
                            <td>{window.end_time}</td>
                            {writable && (
                              <td>
                                <button
                                  className="icon-btn icon-btn--danger"
                                  aria-label={`Delete ${window.day} availability`}
                                  disabled={Boolean(busy)}
                                  onClick={() =>
                                    void removeAvailability(window.id)
                                  }
                                >
                                  <Trash2 size={16} />
                                </button>
                              </td>
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <EmptyState
                    title="No true availability"
                    description="Generation treats missing structured availability as unavailable."
                  />
                )}
              </>
            )}
          </>
        )}
      </Section>

      <Section
        title="Deterministic timetable generation"
        description="Preview is read-only. Apply revalidates the same preview against live scheduling state under the backend write lock."
        actions={
          writable ? (
            <button
              className="btn btn--primary"
              type="button"
              disabled={Boolean(busy)}
              onClick={() => void generatePreview()}
            >
              <WandSparkles size={16} />
              {busy === 'preview'
                ? 'Previewing…'
                : 'Preview timetable generation'}
            </button>
          ) : undefined
        }
      >
        {!preview ? (
          <EmptyState
            title="No generation preview"
            description="Run a preview after offerings, faculty allocation, designation, room and availability are ready."
          />
        ) : (
          <>
            <div className="metrics-grid">
              <Metric label="Status" value={preview.status} />
              <Metric
                label="Already satisfied"
                value={preview.existing_satisfied_count}
              />
              <Metric label="Proposed" value={preview.proposed_count} />
            </div>

            {preview.readiness_errors.length > 0 && (
              <ErrorNote>
                {preview.readiness_errors.join(' ')}
              </ErrorNote>
            )}

            {preview.unscheduled.length > 0 && (
              <div className="error-state" role="alert">
                <div>
                  <strong>Unscheduled components</strong>
                  <ul>
                    {preview.unscheduled.map((item, index) => (
                      <li key={`${item}-${index}`}>{item}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            {preview.proposals.length > 0 && (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Course</th>
                      <th>Faculty</th>
                      <th>Type</th>
                      <th>Day</th>
                      <th>Time</th>
                      <th>Room</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.proposals.map((proposal, index) => (
                      <tr
                        key={`${proposal.offering_id}-${proposal.day}-${proposal.start_time}-${index}`}
                      >
                        <td>
                          <strong>{proposal.course_code}</strong>
                          <small>
                            Semester {proposal.semester} · Section{' '}
                            {proposal.section}
                          </small>
                        </td>
                        <td>{proposal.faculty_name}</td>
                        <td>{proposal.class_type}</td>
                        <td>{proposal.day}</td>
                        <td>
                          {proposal.start_time}–{proposal.end_time}
                        </td>
                        <td>{proposal.room}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <p className="muted">{preview.policy_note}</p>

            {preview.status === 'READY' && preview.complete && (
              <button
                className="btn btn--primary"
                type="button"
                disabled={Boolean(busy)}
                onClick={() => void applyPreview()}
              >
                {busy === 'apply' ? 'Applying…' : 'Apply verified preview'}
              </button>
            )}
          </>
        )}
      </Section>
    </div>
  )
}
