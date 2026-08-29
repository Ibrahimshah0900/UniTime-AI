import { FileUp, KeyRound, Plus, Search } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import {
  studentsApi,
  type StudentIdentityUpdatePayload,
  type StudentProvisionPayload,
} from '../api/students'
import { Field, Input, Select } from '../components/Form'
import {
  EmptyState,
  ErrorNote,
  ErrorState,
  LoadingState,
  Modal,
  PageHeader,
  Pagination,
  Section,
  StatusBadge,
  SuccessNote,
} from '../components/Ui'
import { useAsync } from '../hooks/useAsync'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import type {
  RosterImportResponse,
  StudentAcademicStatus,
  StudentIdentity,
  StudentProvisionResponse,
} from '../types/api'
import { titleCase } from '../utils/format'

const PAGE_SIZE = 25
const academicStatuses: StudentAcademicStatus[] = [
  'active',
  'on_leave',
  'graduated',
  'suspended',
]

export function StudentsPage() {
  const [search, setSearch] = useState('')
  const [verified, setVerified] = useState<boolean | ''>('')
  const [active, setActive] = useState<boolean | ''>('')
  const [offset, setOffset] = useState(0)
  const [createOpen, setCreateOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [editStudent, setEditStudent] = useState<StudentIdentity | null>(null)
  const [credential, setCredential] = useState<StudentProvisionResponse | null>(null)
  const [message, setMessage] = useState('')
  const debouncedSearch = useDebouncedValue(search)

  const students = useAsync(
    () =>
      studentsApi.list({
        search: debouncedSearch,
        isVerified: verified,
        isActive: active,
        offset,
        limit: PAGE_SIZE,
      }),
    [debouncedSearch, verified, active, offset],
  )

  return (
    <div className="page">
      <PageHeader
        title="Students"
        description="Provision verified institutional students, import official rosters, and manage student access."
        actions={
          <div className="button-row">
            <button className="btn btn--secondary" onClick={() => setImportOpen(true)}>
              <FileUp size={16} />
              Import roster
            </button>
            <button className="btn btn--primary" onClick={() => setCreateOpen(true)}>
              <Plus size={16} />
              Provision student
            </button>
          </div>
        }
      />

      {message && <SuccessNote>{message}</SuccessNote>}

      <div className="toolbar toolbar--filters">
        <label className="search-box">
          <Search size={17} />
          <input
            aria-label="Search students"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value)
              setOffset(0)
            }}
            placeholder="Registration, name, email, department or program"
          />
        </label>
        <Select
          aria-label="Verification filter"
          value={String(verified)}
          onChange={(event) => {
            setVerified(event.target.value === '' ? '' : event.target.value === 'true')
            setOffset(0)
          }}
        >
          <option value="">All verification states</option>
          <option value="true">Verified</option>
          <option value="false">Unverified</option>
        </Select>
        <Select
          aria-label="Account status filter"
          value={String(active)}
          onChange={(event) => {
            setActive(event.target.value === '' ? '' : event.target.value === 'true')
            setOffset(0)
          }}
        >
          <option value="">All account states</option>
          <option value="true">Active</option>
          <option value="false">Inactive</option>
        </Select>
      </div>

      <Section>
        {students.loading ? (
          <LoadingState label="Loading students" />
        ) : students.error ? (
          <ErrorState message={students.error} retry={students.reload} />
        ) : students.data?.students.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Student</th>
                  <th>Program</th>
                  <th>Semester</th>
                  <th>Academic status</th>
                  <th>Access</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {students.data.students.map((student) => (
                  <tr key={student.user_id}>
                    <td>
                      <strong>{student.full_name}</strong>
                      <small>{student.registration_number}</small>
                      <small>{student.institutional_email || 'Registration-number login'}</small>
                    </td>
                    <td>
                      {student.program}
                      <small>
                        {student.department} · {student.batch} · Section {student.section}
                      </small>
                    </td>
                    <td>{student.current_semester}</td>
                    <td>
                      <StatusBadge
                        tone={student.academic_status === 'active' ? 'success' : 'neutral'}
                      >
                        {titleCase(student.academic_status)}
                      </StatusBadge>
                    </td>
                    <td>
                      {!student.is_active ? (
                        <StatusBadge tone="neutral">Inactive</StatusBadge>
                      ) : !student.is_verified ? (
                        <StatusBadge tone="warning">Unverified</StatusBadge>
                      ) : student.must_change_password ? (
                        <StatusBadge tone="warning">Password change</StatusBadge>
                      ) : !student.onboarding_completed ? (
                        <StatusBadge tone="info">Onboarding</StatusBadge>
                      ) : (
                        <StatusBadge tone="success">Ready</StatusBadge>
                      )}
                    </td>
                    <td>
                      <button
                        className="btn btn--ghost"
                        onClick={() => setEditStudent(student)}
                      >
                        Manage
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No students match"
            description="Adjust the filters, provision a student, or import an official roster."
          />
        )}
        {students.data && (
          <Pagination
            total={students.data.total}
            offset={students.data.offset}
            limit={students.data.limit}
            label="students"
            onChange={setOffset}
          />
        )}
      </Section>

      {createOpen && (
        <ProvisionStudentModal
          onClose={() => setCreateOpen(false)}
          onSaved={async (result) => {
            setCreateOpen(false)
            setCredential(result)
            setMessage('Student provisioned.')
            await students.reload()
          }}
        />
      )}

      {credential && (
        <CredentialModal result={credential} onClose={() => setCredential(null)} />
      )}

      {importOpen && (
        <RosterImportModal
          onClose={() => setImportOpen(false)}
          onApplied={async () => {
            setMessage('Student roster applied.')
            await students.reload()
          }}
        />
      )}

      {editStudent && (
        <EditStudentModal
          student={editStudent}
          onClose={() => setEditStudent(null)}
          onSaved={async () => {
            setEditStudent(null)
            setMessage('Student updated.')
            await students.reload()
          }}
          onReload={students.reload}
        />
      )}
    </div>
  )
}

function ProvisionStudentModal({
  onClose,
  onSaved,
}: {
  onClose: () => void
  onSaved: (result: StudentProvisionResponse) => Promise<void>
}) {
  const [registration, setRegistration] = useState('')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [department, setDepartment] = useState('')
  const [program, setProgram] = useState('')
  const [batch, setBatch] = useState('')
  const [semester, setSemester] = useState('1')
  const [section, setSection] = useState('')
  const [temporaryPassword, setTemporaryPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    const payload: StudentProvisionPayload = {
      registration_number: registration,
      full_name: name,
      email: email.trim() || null,
      department,
      program,
      batch,
      current_semester: Number(semester),
      section,
      academic_status: 'active',
      is_verified: true,
      is_active: true,
      temporary_password: temporaryPassword || null,
    }
    try {
      const result = await studentsApi.provision(payload)
      await onSaved(result)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to provision student.')
      setBusy(false)
    }
  }

  return (
    <Modal title="Provision institutional student" onClose={onClose} wide>
      <form className="form-grid" onSubmit={submit}>
        <Field label="Registration number">
          <Input value={registration} onChange={(event) => setRegistration(event.target.value)} minLength={3} maxLength={50} required />
        </Field>
        <Field label="Full name">
          <Input value={name} onChange={(event) => setName(event.target.value)} minLength={2} maxLength={200} required />
        </Field>
        <Field label="Institutional email (optional)">
          <Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
        </Field>
        <Field label="Department">
          <Input value={department} onChange={(event) => setDepartment(event.target.value)} required />
        </Field>
        <Field label="Program">
          <Input value={program} onChange={(event) => setProgram(event.target.value)} required />
        </Field>
        <Field label="Batch">
          <Input value={batch} onChange={(event) => setBatch(event.target.value)} required />
        </Field>
        <Field label="Current semester">
          <Input type="number" min={1} max={16} value={semester} onChange={(event) => setSemester(event.target.value)} required />
        </Field>
        <Field label="Section">
          <Input value={section} onChange={(event) => setSection(event.target.value)} required />
        </Field>
        <div className="form-grid__full">
          <Field label="Temporary password (optional)" hint="Leave blank to generate a strong one-time password automatically.">
            <Input type="password" minLength={8} maxLength={128} value={temporaryPassword} onChange={(event) => setTemporaryPassword(event.target.value)} />
          </Field>
        </div>
        {error && <div className="form-grid__full"><ErrorNote>{error}</ErrorNote></div>}
        <div className="modal-actions form-grid__full">
          <button type="button" className="btn btn--secondary" disabled={busy} onClick={onClose}>Cancel</button>
          <button className="btn btn--primary" disabled={busy}>{busy ? 'Provisioning…' : 'Provision student'}</button>
        </div>
      </form>
    </Modal>
  )
}

function CredentialModal({
  result,
  onClose,
}: {
  result: StudentProvisionResponse
  onClose: () => void
}) {
  return (
    <Modal title="Temporary student credential" onClose={onClose}>
      <SuccessNote>Student account created successfully.</SuccessNote>
      <div className="soft-panel">
        <strong>Registration number</strong>
        <p>{result.student.registration_number}</p>
        <strong>Temporary password</strong>
        <p><code data-testid="temporary-password">{result.temporary_password}</code></p>
        <small>
          Share this credential privately with the student. They must change the
          temporary password on first sign-in.
        </small>
      </div>
      <div className="modal-actions">
        <button className="btn btn--primary" onClick={onClose}>Done</button>
      </div>
    </Modal>
  )
}

function RosterImportModal({
  onClose,
  onApplied,
}: {
  onClose: () => void
  onApplied: () => Promise<void>
}) {
  const [file, setFile] = useState<File | null>(null)
  const [updateExisting, setUpdateExisting] = useState(false)
  const [result, setResult] = useState<RosterImportResponse | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function run(dryRun: boolean) {
    if (!file || busy) return
    setBusy(true)
    setError('')
    try {
      const next = await studentsApi.importRoster(file, { dryRun, updateExisting })
      setResult(next)
      if (!dryRun && next.applied) await onApplied()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to import the roster.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title="Import student roster" onClose={onClose} wide>
      <div className="form-stack">
        <Field
          label="Roster file"
          hint="CSV or XLSX. Required: registration number, full name, department, program, batch, current semester and section. Email is optional."
        >
          <Input
            type="file"
            accept=".csv,.xlsx"
            onChange={(event) => {
              setFile(event.target.files?.[0] || null)
              setResult(null)
              setError('')
            }}
          />
        </Field>
        <label className="switch-row">
          <div>
            <strong>Update existing students</strong>
            <span>Match existing identities by registration number.</span>
          </div>
          <input
            type="checkbox"
            checked={updateExisting}
            onChange={(event) => {
              setUpdateExisting(event.target.checked)
              setResult(null)
            }}
          />
        </label>

        {error && <ErrorNote>{error}</ErrorNote>}

        {result && (
          <>
            <div className="report-strip">
              <article><div><strong>Rows read</strong><span>{result.rows_read}</span></div></article>
              <article><div><strong>Would create</strong><span>{result.would_create}</span></div></article>
              <article><div><strong>Would update</strong><span>{result.would_update}</span></div></article>
              <article><div><strong>Duplicates</strong><span>{result.duplicates}</span></div></article>
              <article><div><strong>Invalid</strong><span>{result.invalid}</span></div></article>
            </div>

            {result.errors.length > 0 && (
              <ErrorNote>
                <div>
                  <strong>Roster issues</strong>
                  <ul>
                    {result.errors.slice(0, 12).map((item, index) => (
                      <li key={`${item.row ?? 'file'}-${item.field ?? 'general'}-${index}`}>
                        {item.row ? `Row ${item.row}: ` : ''}
                        {item.field ? `${item.field}: ` : ''}
                        {item.message}
                      </li>
                    ))}
                  </ul>
                  {result.errors.length > 12 && <p>Additional errors are not shown here.</p>}
                </div>
              </ErrorNote>
            )}

            {result.applied && result.credentials.length > 0 && (
              <div className="table-wrap">
                <table className="data-table">
                  <thead><tr><th>Registration</th><th>Temporary password</th></tr></thead>
                  <tbody>
                    {result.credentials.map((item) => (
                      <tr key={item.registration_number}>
                        <td>{item.registration_number}</td>
                        <td><code>{item.temporary_password}</code></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        <div className="modal-actions">
          <button type="button" className="btn btn--secondary" disabled={busy} onClick={onClose}>Close</button>
          <button type="button" className="btn btn--secondary" disabled={!file || busy} onClick={() => void run(true)}>
            {busy ? 'Checking…' : 'Validate roster'}
          </button>
          <button type="button" className="btn btn--primary" disabled={!file || busy || !result?.can_apply || result.applied} onClick={() => void run(false)}>
            Apply roster
          </button>
        </div>
      </div>
    </Modal>
  )
}

function EditStudentModal({
  student,
  onClose,
  onSaved,
  onReload,
}: {
  student: StudentIdentity
  onClose: () => void
  onSaved: () => Promise<void>
  onReload: () => Promise<unknown>
}) {
  const [registration, setRegistration] = useState(student.registration_number)
  const [name, setName] = useState(student.full_name)
  const [email, setEmail] = useState(student.institutional_email || '')
  const [department, setDepartment] = useState(student.department)
  const [program, setProgram] = useState(student.program)
  const [batch, setBatch] = useState(student.batch)
  const [semester, setSemester] = useState(String(student.current_semester))
  const [section, setSection] = useState(student.section)
  const [academicStatus, setAcademicStatus] =
    useState<StudentAcademicStatus>(student.academic_status)
  const [verified, setVerified] = useState(student.is_verified)
  const [active, setActive] = useState(student.is_active)
  const [resetCredential, setResetCredential] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [resetBusy, setResetBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    const payload: StudentIdentityUpdatePayload = {
      registration_number: registration,
      full_name: name,
      email: email.trim() || null,
      department,
      program,
      batch,
      current_semester: Number(semester),
      section,
      academic_status: academicStatus,
      is_verified: verified,
      is_active: active,
    }
    try {
      await studentsApi.update(student.user_id, payload)
      await onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to update student.')
      setBusy(false)
    }
  }

  async function resetPassword() {
    if (resetBusy) return
    setResetBusy(true)
    setError('')
    try {
      const result = await studentsApi.resetTemporaryPassword(student.user_id)
      setResetCredential(result.temporary_password)
      await onReload()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to reset the temporary password.')
    } finally {
      setResetBusy(false)
    }
  }

  return (
    <Modal title={`Manage ${student.registration_number}`} onClose={onClose} wide>
      <form className="form-grid" onSubmit={submit}>
        <Field label="Registration number"><Input value={registration} onChange={(event) => setRegistration(event.target.value)} required /></Field>
        <Field label="Full name"><Input value={name} onChange={(event) => setName(event.target.value)} required /></Field>
        <Field label="Institutional email (optional)"><Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></Field>
        <Field label="Department"><Input value={department} onChange={(event) => setDepartment(event.target.value)} required /></Field>
        <Field label="Program"><Input value={program} onChange={(event) => setProgram(event.target.value)} required /></Field>
        <Field label="Batch"><Input value={batch} onChange={(event) => setBatch(event.target.value)} required /></Field>
        <Field label="Current semester"><Input type="number" min={1} max={16} value={semester} onChange={(event) => setSemester(event.target.value)} required /></Field>
        <Field label="Section"><Input value={section} onChange={(event) => setSection(event.target.value)} required /></Field>
        <Field label="Academic status">
          <Select value={academicStatus} onChange={(event) => setAcademicStatus(event.target.value as StudentAcademicStatus)}>
            {academicStatuses.map((status) => <option key={status} value={status}>{titleCase(status)}</option>)}
          </Select>
        </Field>

        <div className="form-grid__full">
          <label className="switch-row">
            <div><strong>Verified institutional student</strong><span>Required for protected student features after onboarding.</span></div>
            <input type="checkbox" checked={verified} onChange={(event) => setVerified(event.target.checked)} />
          </label>
          <label className="switch-row">
            <div><strong>Account active</strong><span>Inactive accounts cannot authenticate.</span></div>
            <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} />
          </label>
        </div>

        {resetCredential && (
          <div className="soft-panel form-grid__full">
            <strong>New temporary password</strong>
            <p><code>{resetCredential}</code></p>
            <small>The student's existing sessions are invalidated and this password must be changed at next sign-in.</small>
          </div>
        )}

        {error && <div className="form-grid__full"><ErrorNote>{error}</ErrorNote></div>}

        <div className="modal-actions form-grid__full">
          <button type="button" className="btn btn--secondary" disabled={busy || resetBusy} onClick={() => void resetPassword()}>
            <KeyRound size={16} />
            {resetBusy ? 'Resetting…' : 'Reset temporary password'}
          </button>
          <button type="button" className="btn btn--secondary" disabled={busy} onClick={onClose}>Cancel</button>
          <button className="btn btn--primary" disabled={busy || resetBusy}>{busy ? 'Saving…' : 'Save student'}</button>
        </div>
      </form>
    </Modal>
  )
}
