import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { InsightsPage } from '../src/pages/InsightsPage'

const mocks = vi.hoisted(() => ({
  listTerms: vi.fn(),
  dataQuality: vi.fn(),
  resolverAnalytics: vi.fn(),
}))

vi.mock('../src/api/terms', () => ({
  termsApi: { list: mocks.listTerms },
}))
vi.mock('../src/api/insights', () => ({
  insightsApi: {
    dataQuality: mocks.dataQuality,
    resolverAnalytics: mocks.resolverAnalytics,
  },
}))

const terms = {
  terms: [
    {
      id: 1, code: 'FALL-2026', name: 'Fall 2026', status: 'active',
      starts_on: null, ends_on: null, created_by_user_id: null,
      activated_at: null, archived_at: null,
      created_at: '2026-08-01T00:00:00', updated_at: '2026-08-01T00:00:00',
    },
    {
      id: 2, code: 'SPRING-2027', name: 'Spring 2027', status: 'planning',
      starts_on: null, ends_on: null, created_by_user_id: null,
      activated_at: null, archived_at: null,
      created_at: '2026-08-02T00:00:00', updated_at: '2026-08-02T00:00:00',
    },
  ],
  total: 2,
  active_term_id: 1,
}

function analytics(termId: number) {
  return {
    term_id: termId,
    term_code: termId === 2 ? 'SPRING-2027' : 'FALL-2026',
    generated_at: '2026-08-28T12:00:00',
    current_confirmed_conflicts: 0,
    current_inferred_conflicts: 0,
    current_structural_clashes: 0,
    current_verified_students: 0,
    current_enrollment_records: 0,
    current_affected_student_instances: 0,
    report_status_counts: { submitted: 0, under_review: 0, resolved: 0, rejected: 0, duplicate: 0 },
    report_total: 0,
    report_cluster_count: 0,
    grouped_duplicate_reports: 0,
    average_first_resolution_hours: null,
    resolution_applications: 0,
    resolution_undos: 0,
    resolution_redos: 0,
    confirmed_conflicts_removed_by_applications: 0,
    structural_clashes_removed_by_applications: 0,
    shared_resolved_reports: 0,
    shared_resolution_percentage: null,
    recommendation_acceptance_rate: {
      value: null, numerator: null, denominator: null, available: false,
      reason: 'No recommendation events.',
    },
    undo_rate: {
      value: null, numerator: null, denominator: null, available: false,
      reason: 'No resolution applications.',
    },
    redo_rate: {
      value: null, numerator: null, denominator: null, available: false,
      reason: 'No undo events.',
    },
    important_note: 'Measured data only.',
  }
}

function quality(termId: number) {
  return {
    term_id: termId,
    term_code: termId === 2 ? 'SPRING-2027' : 'FALL-2026',
    generated_at: '2026-08-28T12:00:00',
    summary: {
      total: termId === 2 ? 1 : 0,
      critical: 0,
      error: termId === 2 ? 1 : 0,
      warning: 0,
      info: 0,
    },
    issues: termId === 2
      ? [{
          issue_code: 'OFFERING_WITHOUT_FACULTY_ALLOCATION',
          severity: 'error',
          scope: 'term',
          entity_type: 'course_offering',
          entity_id: '11',
          message: 'CS-210 has no faculty allocation.',
          suggested_correction: 'Allocate one faculty member.',
          related_entity_ids: [11],
        }]
      : [],
    important_note: 'Read-only report.',
  }
}

describe('InsightsPage academic term diagnostics', () => {
  beforeEach(() => {
    mocks.listTerms.mockReset().mockResolvedValue(terms)
    mocks.dataQuality.mockReset().mockImplementation(
      (termId: number) => Promise.resolve(quality(termId)),
    )
    mocks.resolverAnalytics.mockReset().mockImplementation(
      (termId: number) => Promise.resolve(analytics(termId)),
    )
  })

  it('switches from active analytics to planning scheduling readiness', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <InsightsPage />
      </MemoryRouter>,
    )

    await waitFor(() => expect(mocks.dataQuality).toHaveBeenLastCalledWith(1))
    expect(screen.getByLabelText('Academic term')).toHaveValue('1')
    expect(screen.queryByRole('link', { name: 'Open scheduling' })).toBeNull()

    await user.selectOptions(screen.getByLabelText('Academic term'), '2')

    await waitFor(() => expect(mocks.dataQuality).toHaveBeenLastCalledWith(2))
    await waitFor(() => expect(mocks.resolverAnalytics).toHaveBeenLastCalledWith(2))

    expect(screen.getByText('SPRING-2027 - planning')).toBeVisible()
    expect(screen.getByText('Scheduling findings')).toBeVisible()
    expect(screen.getByText('OFFERING WITHOUT FACULTY ALLOCATION')).toBeVisible()
    expect(screen.getByText(/Scheduling readiness/)).toBeVisible()
    expect(screen.getByRole('link', { name: 'Open scheduling' })).toHaveAttribute(
      'href',
      '/scheduling',
    )
  })
})
