import { Plus, Trash2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { institutionalSchedulingApi } from '../api/institutionalScheduling'
import { termsApi } from '../api/terms'
import { Field, Input, Select } from '../components/Form'
import {
  EmptyState,
  ErrorNote,
  ErrorState,
  LoadingState,
  PageHeader,
  Section,
  StatusBadge,
  SuccessNote,
} from '../components/Ui'
import { useAsync } from '../hooks/useAsync'
import type { FacultyAvailabilityDay } from '../types/api'

const weekdays: FacultyAvailabilityDay[] = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
]

export function FacultyAvailabilityPage() {
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

  const windows = useAsync(
    () =>
      effectiveTermId
        ? institutionalSchedulingApi.myAvailability(effectiveTermId)
        : Promise.resolve([]),
    [effectiveTermId],
  )

  const [day, setDay] = useState<FacultyAvailabilityDay>('Monday')
  const [start, setStart] = useState('08:00')
  const [end, setEnd] = useState('12:00')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  async function add(event: FormEvent) {
    event.preventDefault()
    if (!effectiveTermId || !writable || busy) return
    setBusy(true)
    setMessage('')
    setError('')
    try {
      await institutionalSchedulingApi.addMyAvailability({
        term_id: effectiveTermId,
        day,
        start_time: start,
        end_time: end,
      })
      setMessage('Availability window added.')
      await windows.reload()
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Unable to add availability.',
      )
    } finally {
      setBusy(false)
    }
  }

  async function remove(id: number) {
    if (!window.confirm('Delete this availability window?')) return
    setBusy(true)
    setMessage('')
    setError('')
    try {
      await institutionalSchedulingApi.deleteMyAvailability(id)
      setMessage('Availability window removed.')
      await windows.reload()
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'Unable to remove availability.',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <PageHeader
        title="My availability"
        description="Declare the real times you are available to teach. Timetable gaps are not treated as availability."
      />
      {message && <SuccessNote>{message}</SuccessNote>}
      {error && <ErrorNote>{error}</ErrorNote>}
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
          <StatusBadge tone={writable ? 'warning' : 'neutral'}>
            {selectedTerm.code} - {selectedTerm.status}
          </StatusBadge>
        )}
      </div>

      {writable ? (
        <Section
          title="Add availability"
          description="Windows cannot overlap and must stay within institutional operating hours."
        >
          <form className="form-grid" onSubmit={add}>
            <Field label="Day">
              <Select
                value={day}
                onChange={(event) =>
                  setDay(event.target.value as FacultyAvailabilityDay)
                }
              >
                {weekdays.map((value) => (
                  <option value={value} key={value}>
                    {value}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Available from">
              <Input
                type="time"
                value={start}
                onChange={(event) => setStart(event.target.value)}
                required
              />
            </Field>
            <Field label="Available until">
              <Input
                type="time"
                value={end}
                onChange={(event) => setEnd(event.target.value)}
                required
              />
            </Field>
            <div className="form-grid__full">
              <button className="btn btn--primary" disabled={busy}>
                <Plus size={16} />
                {busy ? 'Saving…' : 'Add availability'}
              </button>
            </div>
          </form>
        </Section>
      ) : selectedTerm ? (
        <ErrorNote>
          Availability can be changed only while the academic term is in
          planning. Existing windows remain readable.
        </ErrorNote>
      ) : null}

      <Section title="Declared availability">
        {windows.loading ? (
          <LoadingState label="Loading availability" />
        ) : windows.error ? (
          <ErrorState message={windows.error} retry={windows.reload} />
        ) : windows.data?.length ? (
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
                {windows.data.map((window) => (
                  <tr key={window.id}>
                    <td>{window.day}</td>
                    <td>{window.start_time}</td>
                    <td>{window.end_time}</td>
                    {writable && (
                      <td>
                        <button
                          className="icon-btn icon-btn--danger"
                          aria-label={`Delete ${window.day} availability`}
                          disabled={busy}
                          onClick={() => void remove(window.id)}
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
            title="No availability declared"
            description="Add planning-term availability so institutional generation can schedule your assigned subjects."
          />
        )}
      </Section>
    </div>
  )
}
