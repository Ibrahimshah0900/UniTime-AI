import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { FacultyAvailabilityPage } from '../src/pages/FacultyAvailabilityPage'

const mocks = vi.hoisted(() => ({
  listTerms: vi.fn(),
  myAvailability: vi.fn(),
  addMyAvailability: vi.fn(),
  deleteMyAvailability: vi.fn(),
}))

vi.mock('../src/api/terms', () => ({
  termsApi: { list: mocks.listTerms },
}))

vi.mock('../src/api/institutionalScheduling', () => ({
  institutionalSchedulingApi: {
    myAvailability: mocks.myAvailability,
    addMyAvailability: mocks.addMyAvailability,
    deleteMyAvailability: mocks.deleteMyAvailability,
  },
}))

describe('FacultyAvailabilityPage', () => {
  beforeEach(() => {
    mocks.listTerms.mockReset().mockResolvedValue({
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
    })
    mocks.myAvailability.mockReset().mockResolvedValue([])
    mocks.addMyAvailability.mockReset().mockResolvedValue({})
    mocks.deleteMyAvailability.mockReset().mockResolvedValue(undefined)
  })

  it('defaults to planning and lets faculty declare true availability', async () => {
    const user = userEvent.setup()
    render(<FacultyAvailabilityPage />)

    await waitFor(() =>
      expect(mocks.myAvailability).toHaveBeenLastCalledWith(2),
    )
    expect(screen.getByLabelText('Academic term')).toHaveValue('2')

    await user.selectOptions(screen.getByLabelText('Day'), 'Thursday')
    await user.clear(screen.getByLabelText('Available from'))
    await user.type(screen.getByLabelText('Available from'), '09:00')
    await user.clear(screen.getByLabelText('Available until'))
    await user.type(screen.getByLabelText('Available until'), '13:00')
    await user.click(screen.getByRole('button', { name: 'Add availability' }))

    await waitFor(() =>
      expect(mocks.addMyAvailability).toHaveBeenCalledWith({
        term_id: 2,
        day: 'Thursday',
        start_time: '09:00',
        end_time: '13:00',
      }),
    )
  })
})
