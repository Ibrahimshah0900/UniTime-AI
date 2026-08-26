import { useState, type FormEvent } from 'react'
import { termsApi } from '../api/terms'
import { ApiError } from '../api/client'
import { Field, Input } from '../components/Form'
import { EmptyState, ErrorNote, ErrorState, LoadingState, PageHeader, Section, SuccessNote } from '../components/Ui'
import { useAsync } from '../hooks/useAsync'

export function AcademicTermsPage() {
  const terms = useAsync(() => termsApi.list(), [])
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [startsOn, setStartsOn] = useState('')
  const [endsOn, setEndsOn] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  async function createTerm(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await termsApi.create({ code, name, starts_on: startsOn || null, ends_on: endsOn || null })
      setCode('')
      setName('')
      setStartsOn('')
      setEndsOn('')
      setMessage('Planning academic term created.')
      await terms.reload()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to create academic term.')
    } finally {
      setBusy(false)
    }
  }

  async function archiveTerm(id: number) {
    if (!window.confirm('Archive this active term? It will become read-only.')) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await termsApi.archive(id)
      setMessage('Academic term archived.')
      await terms.reload()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to archive academic term.')
    } finally {
      setBusy(false)
    }
  }

  async function activateTerm(id: number) {
    if (!window.confirm('Activate this planning term? The current active term must be archived first.')) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await termsApi.activate(id)
      setMessage('Academic term activated.')
      await terms.reload()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to activate academic term.')
    } finally {
      setBusy(false)
    }
  }

  return <div className="page">
    <PageHeader title="Academic terms" description="Manage the strict planning, active, and archived term lifecycle."/>
    <div className="two-column two-column--narrow">
      <Section title="Create planning term">
        <form className="form-stack" onSubmit={createTerm}>
          <Field label="Term code"><Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="SPRING-2027" required/></Field>
          <Field label="Term name"><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Spring 2027" required/></Field>
          <Field label="Starts on"><Input type="date" value={startsOn} onChange={(e) => setStartsOn(e.target.value)}/></Field>
          <Field label="Ends on"><Input type="date" value={endsOn} onChange={(e) => setEndsOn(e.target.value)}/></Field>
          {error && <ErrorNote>{error}</ErrorNote>}
          {message && <SuccessNote>{message}</SuccessNote>}
          <button className="btn btn--primary" disabled={busy}>{busy ? "Creating..." : "Create planning term"}</button>
        </form>
      </Section>
      <Section title="Term lifecycle" description="Archived terms are read-only and retain historical records.">
        {terms.loading ? <LoadingState/> : terms.error ? <ErrorState message={terms.error} retry={terms.reload}/> : terms.data?.terms.length ? <div className="enrollment-list">{terms.data.terms.map((term) => <article key={term.id}>
          <div className="course-token">{term.code.slice(0, 2)}</div>
          <div><strong>{term.name}</strong><span>{term.code} - {term.status}</span><small>{term.starts_on || "No start date"} - {term.ends_on || "No end date"}</small></div>
          <div className="modal-actions">
            {term.status === 'active' && <button className="btn btn--danger" disabled={busy} onClick={() => void archiveTerm(term.id)}>Archive</button>}
            {term.status === 'planning' && <button className="btn btn--primary" disabled={busy} onClick={() => void activateTerm(term.id)}>Activate</button>}
          </div>
        </article>)}</div> : <EmptyState title="No academic terms" description="Create a planning term to begin the next semester lifecycle."/>}
      </Section>
    </div>
  </div>
}
