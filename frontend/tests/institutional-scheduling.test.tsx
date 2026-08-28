import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { InstitutionalSchedulingPage } from '../src/pages/InstitutionalSchedulingPage'

const mocks = vi.hoisted(() => ({
  listTerms: vi.fn(),
  courseOfferings: vi.fn(),
  createCourseOffering: vi.fn(),
  deleteCourseOffering: vi.fn(),
  workloads: vi.fn(),
  setDesignation: vi.fn(),
  managedAvailability: vi.fn(),
  addManagedAvailability: vi.fn(),
  deleteManagedAvailability: vi.fn(),
  previewGeneration: vi.fn(),
  applyGeneration: vi.fn(),
}))

vi.mock('../src/api/terms', () => ({
  termsApi: { list: mocks.listTerms },
}))

vi.mock('../src/api/institutionalScheduling', () => ({
  institutionalSchedulingApi: {
    courseOfferings: mocks.courseOfferings,
    createCourseOffering: mocks.createCourseOffering,
    deleteCourseOffering: mocks.deleteCourseOffering,
    workloads: mocks.workloads,
    setDesignation: mocks.setDesignation,
    managedAvailability: mocks.managedAvailability,
    addManagedAvailability: mocks.addManagedAvailability,
    deleteManagedAvailability: mocks.deleteManagedAvailability,
    previewGeneration: mocks.previewGeneration,
    applyGeneration: mocks.applyGeneration,
  },
}))

const terms = {
  terms: [
    {
      id: 1,
      code: 'FALL-2026',
      name: 'Fall 2026',
      status: 'active',
      starts_on: null,
      ends_on: null,
      created_by_user_id: null,
      activated_at: null,
      archived_at: null,
      created_at: '2026-08-01T00:00:00',
      updated_at: '2026-08-01T00:00:00',
    },
    {
      id: 2,
      code: 'SPRING-2027',
      name: 'Spring 2027',
      status: 'planning',
      starts_on: null,
      ends_on: null,
      created_by_user_id: null,
      activated_at: null,
      archived_at: null,
      created_at: '2026-08-02T00:00:00',
      updated_at: '2026-08-02T00:00:00',
    },
  ],
  total: 2,
  active_term_id: 1,
}

const workload = {
  faculty_user_id: 7,
  faculty_name: 'Dr Ada',
  faculty_email: 'ada@example.edu',
  designation: null,
  profile_configured: false,
  term_id: 2,
  distinct_subjects_assigned: 0,
  maximum_subjects: null,
  remaining_capacity: null,
  subject_codes: [],
}

describe('InstitutionalSchedulingPage', () => {
  beforeEach(() => {
    mocks.listTerms.mockReset().mockResolvedValue(terms)
    mocks.courseOfferings.mockReset().mockResolvedValue([])
    mocks.createCourseOffering.mockReset().mockResolvedValue({})
    mocks.deleteCourseOffering.mockReset().mockResolvedValue(undefined)
    mocks.workloads.mockReset().mockResolvedValue([workload])
    mocks.setDesignation
      .mockReset()
      .mockResolvedValue({ ...workload, designation: 'lecturer' })
    mocks.managedAvailability.mockReset().mockResolvedValue([])
    mocks.addManagedAvailability.mockReset().mockResolvedValue({})
    mocks.deleteManagedAvailability.mockReset().mockResolvedValue(undefined)
    mocks.previewGeneration.mockReset().mockResolvedValue({
      term_id: 2,
      status: 'READY',
      preview_id: 'a'.repeat(64),
      complete: true,
      existing_satisfied_entry_ids: [],
      existing_satisfied_count: 0,
      proposed_count: 1,
      readiness_errors: [],
      unscheduled: [],
      proposals: [
        {
          offering_id: 11,
          faculty_user_id: 7,
          faculty_name: 'Dr Ada',
          course_code: 'CS-210',
          course_name: 'Algorithms',
          semester: 2,
          section: 'A',
          class_type: 'lecture',
          room: 'R-201',
          day: 'Tuesday',
          start_time: '08:00',
          end_time: '09:00',
          duration_minutes: 60,
        },
      ],
      policy_note: 'Deterministic policy preview.',
    })
    mocks.applyGeneration.mockReset().mockResolvedValue({
      success: true,
      term_id: 2,
      preview_id: 'a'.repeat(64),
      created_count: 1,
      existing_satisfied_count: 0,
      entries: [],
      message: 'Timetable generation applied.',
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('defaults to the planning term and creates a structured course offering', async () => {
    const user = userEvent.setup()
    render(<InstitutionalSchedulingPage />)

    await waitFor(() =>
      expect(mocks.courseOfferings).toHaveBeenLastCalledWith(2),
    )
    expect(screen.getByLabelText('Academic term')).toHaveValue('2')

    await user.type(screen.getByLabelText('Course code'), 'CS-210')
    await user.type(screen.getByLabelText('Course name'), 'Algorithms')
    await user.selectOptions(screen.getByLabelText('Semester'), '2')
    await user.type(screen.getByLabelText('Room/location'), 'R-201')
    await user.click(screen.getByRole('button', { name: 'Add offering' }))

    await waitFor(() =>
      expect(mocks.createCourseOffering).toHaveBeenCalledWith({
        term_id: 2,
        course_code: 'CS-210',
        course_name: 'Algorithms',
        semester: 2,
        section: 'A',
        class_type: 'lecture',
        duration_minutes: 60,
        room: 'R-201',
      }),
    )
  })

  it('configures faculty designation and true availability', async () => {
    const user = userEvent.setup()
    render(<InstitutionalSchedulingPage />)

    await screen.findByRole('option', { name: /Dr Ada/ })
    await user.selectOptions(screen.getByLabelText('Faculty member'), '7')
    await user.selectOptions(
      screen.getByLabelText('Teaching designation'),
      'lecturer',
    )
    await user.click(screen.getByRole('button', { name: 'Save designation' }))

    await waitFor(() =>
      expect(mocks.setDesignation).toHaveBeenCalledWith(7, 'lecturer', 2),
    )

    await user.selectOptions(
      screen.getByLabelText('Availability day'),
      'Wednesday',
    )
    await user.click(screen.getByRole('button', { name: 'Add availability' }))

    await waitFor(() =>
      expect(mocks.addManagedAvailability).toHaveBeenCalledWith({
        faculty_user_id: 7,
        term_id: 2,
        day: 'Wednesday',
        start_time: '08:00',
        end_time: '12:00',
      }),
    )
  })

  it('previews then applies the exact deterministic preview id', async () => {
    const user = userEvent.setup()
    render(<InstitutionalSchedulingPage />)

    await user.click(
      await screen.findByRole('button', {
        name: 'Preview timetable generation',
      }),
    )

    await waitFor(() =>
      expect(mocks.previewGeneration).toHaveBeenCalledWith(2),
    )
    expect(await screen.findByText('CS-210')).toBeInTheDocument()
    await user.click(
      screen.getByRole('button', { name: 'Apply verified preview' }),
    )

    await waitFor(() =>
      expect(mocks.applyGeneration).toHaveBeenCalledWith(2, 'a'.repeat(64)),
    )
    expect(
      await screen.findByText('Timetable generation applied.'),
    ).toBeInTheDocument()
  })
})
