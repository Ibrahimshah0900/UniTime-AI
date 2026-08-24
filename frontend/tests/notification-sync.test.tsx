import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AppShell } from '../src/layouts/AppShell'
import { NotificationsPage } from '../src/pages/NotificationsPage'

const mocks = vi.hoisted(() => ({
  markedRead: false,
  list: vi.fn(),
  markRead: vi.fn(),
  preferences: vi.fn(),
  logout: vi.fn(),
  user: {
    id: 1,
    email: 'student@example.edu',
    full_name: 'Test Student',
    role: 'student' as const,
    is_active: true,
    created_at: '2026-08-25T03:00:00',
    updated_at: '2026-08-25T03:00:00',
  },
}))

vi.mock('../src/features/auth/AuthContext', () => ({
  useAuth: () => ({
    user: mocks.user,
    logout: mocks.logout,
  }),
}))

vi.mock('../src/api/notifications', () => ({
  notificationsApi: {
    list: mocks.list,
    markRead: mocks.markRead,
    markAllRead: vi.fn(),
    preferences: mocks.preferences,
    updatePreferences: vi.fn(),
    processJobs: vi.fn(),
  },
}))

const notification = {
  id: 7,
  user_id: 1,
  type: 'clash_report_status' as const,
  title: 'Report updated',
  message: 'Your clash report is under review.',
  payload: {},
  read_at: null,
  created_at: '2026-08-25T03:00:00',
}

describe('notification badge synchronization', () => {
  beforeEach(() => {
    mocks.markedRead = false
    mocks.list.mockReset().mockImplementation(async () => ({
      notifications: [{ ...notification, read_at: mocks.markedRead ? '2026-08-25T04:00:00' : null }],
      total: 1,
      unread_count: mocks.markedRead ? 0 : 1,
      offset: 0,
      limit: 20,
    }))
    mocks.markRead.mockReset().mockImplementation(async () => {
      mocks.markedRead = true
      return { ...notification, read_at: '2026-08-25T04:00:00' }
    })
    mocks.preferences.mockReset().mockResolvedValue({
      user_id: 1,
      class_reminder_minutes: null,
      daily_summary_enabled: false,
      daily_summary_time: '07:00',
      schedule_change_enabled: true,
      clash_report_updates_enabled: true,
      updated_at: null,
    })
  })

  it('refreshes the top-bar unread badge after a notification is marked read', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/notifications']}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/notifications" element={<NotificationsPage />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    const notificationButton = screen.getByRole('button', { name: 'Notifications' })
    await waitFor(() => expect(notificationButton).toHaveTextContent('1'))

    await user.click(await screen.findByRole('button', { name: 'Mark read' }))

    await waitFor(() => expect(notificationButton).not.toHaveTextContent('1'))
    expect(mocks.markRead).toHaveBeenCalledWith(7)
    expect(mocks.list.mock.calls.filter(([params]) => params?.limit === 5)).toHaveLength(2)
  })
})
