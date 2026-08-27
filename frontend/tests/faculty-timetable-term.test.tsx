import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { TimetablePage } from '../src/pages/TimetablePage'

const mocks = vi.hoisted(() => ({
  timetable: vi.fn(),
  listTerms: vi.fn(),
}))

vi.mock('../src/features/auth/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'faculty' } }),
}))

vi.mock('../src/api/faculty', () => ({
  facultyApi: { timetable: mocks.timetable },
}))

vi.mock('../src/api/terms', () => ({
  termsApi: { list: mocks.listTerms },
}))

const terms = {
  terms: [
    { id: 1, code: 'FALL-2026', name: 'Fall 2026', status: 'active', starts_on: null, ends_on: null, created_by_user_id: null, activated_at: null, archived_at: null, created_at: '2026-08-01T00:00:00', updated_at: '2026-08-01T00:00:00' },
    { id: 2, code: 'SPRING-2027', name: 'Spring 2027', status: 'planning', starts_on: null, ends_on: null, created_by_user_id: null, activated_at: null, archived_at: null, created_at: '2026-08-02T00:00:00', updated_at: '2026-08-02T00:00:00' },
  ],
  total: 2,
  active_term_id: 1,
}

describe('faculty timetable term selection', () => {
  beforeEach(() => {
    mocks.listTerms.mockReset().mockResolvedValue(terms)
    mocks.timetable.mockReset().mockResolvedValue([])
  })

  it('loads the faculty timetable for the selected term', async () => {
    const user = userEvent.setup()
    render(<TimetablePage />)

    await waitFor(() => expect(mocks.timetable).toHaveBeenLastCalledWith(1))

    await user.selectOptions(screen.getByLabelText('Academic term'), '2')

    await waitFor(() => expect(mocks.timetable).toHaveBeenLastCalledWith(2))
  })
})
