import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DashboardPage } from '../src/pages/DashboardPage'

const mocks = vi.hoisted(() => ({
  dashboard: vi.fn(),
  studentTimetable: vi.fn(),
  studentReports: vi.fn(),
  facultyTimetable: vi.fn(),
  notifications: vi.fn(),
  reportQueue: vi.fn(),
}))

vi.mock('../src/features/auth/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 1,
      email: 'ibrahim@example.edu',
      full_name: 'Ibrahim Shah',
      role: 'student',
      is_active: true,
      created_at: '2026-08-01T00:00:00',
      updated_at: '2026-08-01T00:00:00',
    },
  }),
}))

vi.mock('../src/api/dashboards', () => ({
  dashboardApi: { get: mocks.dashboard },
}))

vi.mock('../src/api/student', () => ({
  studentApi: {
    timetable: mocks.studentTimetable,
    clashReports: mocks.studentReports,
  },
}))

vi.mock('../src/api/faculty', () => ({
  facultyApi: { timetable: mocks.facultyTimetable },
}))

vi.mock('../src/api/notifications', () => ({
  notificationsApi: { list: mocks.notifications },
}))

vi.mock('../src/api/reports', () => ({
  reportsApi: { queue: mocks.reportQueue },
}))

describe('Dashboard Experience v2', () => {
  beforeEach(() => {
    mocks.dashboard.mockReset().mockResolvedValue({
      role: 'student',
      generated_for_day: 'Friday',
      data: {
        enrolled_classes: 4,
        open_reports: 0,
      },
    })

    mocks.studentTimetable.mockReset().mockResolvedValue([
      {
        id: 1,
        term_id: 1,
        entry_kind: 'course',
        course_code: 'CS-210',
        course_name: 'Data Structures',
        semester: 'Fall 2026',
        section: 'A',
        faculty: 'Dr. Sara',
        room: 'CS-301',
        day: 'Monday',
        start_time: '09:00',
        end_time: '10:00',
        class_type: 'lecture',
        raw_text: null,
        source: 'manual',
      },
    ])

    mocks.studentReports.mockReset().mockResolvedValue({
      reports: [],
      total: 0,
      offset: 0,
      limit: 4,
    })

    mocks.facultyTimetable.mockReset().mockResolvedValue([])

    mocks.notifications.mockReset().mockResolvedValue({
      notifications: [
        {
          id: 4,
          term_id: 1,
          user_id: 1,
          type: 'schedule_change',
          title: 'Schedule updated',
          message: 'Your timetable has a verified update.',
          payload: {},
          read_at: null,
          created_at: '2026-08-27T10:00:00',
        },
      ],
      total: 1,
      unread_count: 1,
      offset: 0,
      limit: 4,
    })

    mocks.reportQueue.mockReset().mockResolvedValue({
      reports: [],
      total: 0,
      offset: 0,
      limit: 4,
    })
  })

  it('renders the premium student dashboard without changing core navigation', async () => {
    render(
      <MemoryRouter>
        <DashboardPage/>
      </MemoryRouter>,
    )

    await waitFor(() => expect(mocks.dashboard).toHaveBeenCalledTimes(1))

    expect(
      await screen.findByRole('heading', { name: /Good .* Ibrahim/ }),
    ).toBeInTheDocument()

    expect(
      screen.getByText('Your week, without the noise.'),
    ).toBeInTheDocument()

    expect(
      screen.getByRole('link', { name: /View my schedule/i }),
    ).toHaveAttribute('href', '/timetable')

    expect(
      await screen.findByText('Data Structures'),
    ).toBeInTheDocument()

    expect(
      await screen.findByText('Schedule updated'),
    ).toBeInTheDocument()

    expect(
      screen.getByText('Student command center'),
    ).toBeInTheDocument()
  })
})
