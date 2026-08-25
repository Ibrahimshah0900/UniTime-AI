import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EnrollmentsPage } from '../src/pages/EnrollmentsPage'


const mocks = vi.hoisted(() => ({
  enrollments: vi.fn(),
  validateEnrollment: vi.fn(),
  addEnrollment: vi.fn(),
  removeEnrollment: vi.fn(),
}))

vi.mock('../src/api/student', () => ({
  studentApi: mocks,
}))

const conflictValidation = {
  course_code: 'CS-210',
  section: 'A',
  semester: 'Fall 2026',
  mapped_timetable_entry_ids: [2],
  has_conflicts: true,
  conflicts: [
    {
      proposed_class: {
        id: 2,
        course_code: 'CS-210',
        course_name: 'Algorithms',
        section: 'A',
        semester: 'Fall 2026',
        faculty: null,
        room: null,
        day: 'Tuesday' as const,
        start_time: '10:30',
        end_time: '11:30',
      },
      conflicts_with: {
        id: 1,
        course_code: 'AI-301',
        course_name: 'Artificial Intelligence',
        section: 'A',
        semester: 'Fall 2026',
        faculty: null,
        room: null,
        day: 'Tuesday' as const,
        start_time: '10:00',
        end_time: '11:30',
      },
      day: 'Tuesday' as const,
      overlap_start: '10:30',
      overlap_end: '11:30',
    },
  ],
  alternate_sections: [
    {
      section: 'B',
      timetable_entry_ids: [3],
      conflict_free: true,
      validation_status: 'timetable_only_unverified' as const,
      limitations: ['Section capacity and seat availability are not modeled.'],
    },
  ],
  limitations: ['Alternate sections are timetable-only possibilities.'],
}

async function fillAndSubmit() {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Course code'), 'CS-210')
  await user.type(screen.getByLabelText('Section'), 'A')
  await user.type(screen.getByLabelText('Semester'), 'Fall 2026')
  await user.click(screen.getByRole('button', { name: 'Add enrollment' }))
}

describe('enrollment conflict validation', () => {
  beforeEach(() => {
    mocks.enrollments.mockReset().mockResolvedValue([])
    mocks.validateEnrollment.mockReset().mockResolvedValue(conflictValidation)
    mocks.addEnrollment.mockReset().mockResolvedValue({
      id: 9,
      term_id: 1,
      user_id: 1,
      course_code: 'CS-210',
      section: 'A',
      semester: 'Fall 2026',
      created_at: '2026-08-25T10:00:00',
      conflict_validation: conflictValidation,
    })
    mocks.removeEnrollment.mockReset()
  })

  it('shows the exact overlap and does not enroll when the student cancels', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<EnrollmentsPage />)
    await fillAndSubmit()

    await waitFor(() => expect(mocks.validateEnrollment).toHaveBeenCalled())
    expect(confirm).toHaveBeenCalledWith(
      expect.stringContaining('CS-210 overlaps AI-301 on Tuesday 10:30–11:30'),
    )
    expect(confirm).toHaveBeenCalledWith(
      expect.stringContaining('Timetable-only conflict-free section(s): B'),
    )
    expect(mocks.addEnrollment).not.toHaveBeenCalled()
    confirm.mockRestore()
  })

  it('keeps the requested section and surfaces the conflict after confirmation', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<EnrollmentsPage />)
    await fillAndSubmit()

    await waitFor(() => expect(mocks.addEnrollment).toHaveBeenCalledWith({
      course_code: 'CS-210',
      section: 'A',
      semester: 'Fall 2026',
    }))
    expect(await screen.findByText(/Enrollment added with a verified timetable conflict/)).toBeInTheDocument()
    confirm.mockRestore()
  })
})
