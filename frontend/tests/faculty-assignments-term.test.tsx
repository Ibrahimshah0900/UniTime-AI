import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { FacultyAssignmentsPage } from '../src/pages/FacultyAssignmentsPage'

const mocks = vi.hoisted(() => ({
  role: 'coordinator' as 'coordinator' | 'faculty',
  assignments: vi.fn(),
  managedAssignments: vi.fn(),
  directory: vi.fn(),
  addAssignment: vi.fn(),
  removeAssignment: vi.fn(),
  courseOfferings: vi.fn(),
  listTerms: vi.fn(),
}))

vi.mock('../src/features/auth/AuthContext', () => ({
  useAuth: () => ({ user: { role: mocks.role } }),
}))

vi.mock('../src/api/faculty', () => ({
  facultyApi: {
    assignments: mocks.assignments,
    managedAssignments: mocks.managedAssignments,
    directory: mocks.directory,
    addAssignment: mocks.addAssignment,
    removeAssignment: mocks.removeAssignment,
  },
}))

vi.mock('../src/api/institutionalScheduling', () => ({
  institutionalSchedulingApi: {
    courseOfferings: mocks.courseOfferings,
  },
}))

vi.mock('../src/api/terms', () => ({
  termsApi: { list: mocks.listTerms },
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

describe('FacultyAssignmentsPage term selection', () => {
  beforeEach(() => {
    mocks.role = 'coordinator'
    mocks.listTerms.mockReset().mockResolvedValue(terms)
    mocks.assignments.mockReset().mockResolvedValue([])
    mocks.managedAssignments.mockReset().mockResolvedValue([])
    mocks.directory.mockReset().mockResolvedValue({
      faculty: [
        { id: 7, full_name: 'Dr Ada', email: 'ada@example.edu' },
      ],
      total: 1,
      offset: 0,
      limit: 100,
    })
    mocks.addAssignment.mockReset().mockResolvedValue({})
    mocks.removeAssignment.mockReset()
    mocks.courseOfferings.mockReset().mockImplementation((termId: number) =>
      Promise.resolve(
        termId === 2
          ? [
              {
                id: 11,
                term_id: 2,
                course_code: 'CS-210',
                course_name: 'Algorithms',
                semester: 2,
                section: 'A',
                class_type: 'lecture',
                duration_minutes: 60,
                room: 'R-201',
                created_by_user_id: 1,
                created_at: '2026-08-02T00:00:00',
                updated_at: '2026-08-02T00:00:00',
              },
              {
                id: 12,
                term_id: 2,
                course_code: 'CS-210',
                course_name: 'Algorithms Lab',
                semester: 2,
                section: 'A',
                class_type: 'lab',
                duration_minutes: 120,
                room: 'LAB-1',
                created_by_user_id: 1,
                created_at: '2026-08-02T00:00:00',
                updated_at: '2026-08-02T00:00:00',
              },
            ]
          : [],
      ),
    )
  })

  it('uses structured planning offerings for assignment creation', async () => {
    const user = userEvent.setup()
    render(<FacultyAssignmentsPage />)

    await waitFor(() =>
      expect(mocks.managedAssignments).toHaveBeenLastCalledWith(undefined, 1),
    )
    expect(screen.getByLabelText('Find faculty')).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Add assignment' }),
    ).toBeNull()

    await user.selectOptions(screen.getByLabelText('Academic term'), '2')
    await waitFor(() =>
      expect(mocks.managedAssignments).toHaveBeenLastCalledWith(undefined, 2),
    )
    await waitFor(() =>
      expect(mocks.courseOfferings).toHaveBeenLastCalledWith(2),
    )

    await user.selectOptions(screen.getByLabelText('Faculty member'), '7')
    await user.selectOptions(screen.getByLabelText('Course offering'), '11')
    await user.click(screen.getByRole('button', { name: 'Add assignment' }))

    await waitFor(() =>
      expect(mocks.addAssignment).toHaveBeenCalledWith({
        faculty_user_id: 7,
        term_id: 2,
        course_code: 'CS-210',
        section: 'A',
        semester: '2',
      }),
    )
  })

  it('lets faculty switch terms for their own assignments', async () => {
    mocks.role = 'faculty'
    const user = userEvent.setup()
    render(<FacultyAssignmentsPage />)

    await waitFor(() => expect(mocks.assignments).toHaveBeenLastCalledWith(1))

    await user.selectOptions(screen.getByLabelText('Academic term'), '2')

    await waitFor(() => expect(mocks.assignments).toHaveBeenLastCalledWith(2))
    expect(
      screen.queryByRole('button', { name: 'Add assignment' }),
    ).toBeNull()
  })
})
