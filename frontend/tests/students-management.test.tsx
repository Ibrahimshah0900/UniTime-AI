import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { studentsApi } from '../src/api/students'
import { StudentsPage } from '../src/pages/StudentsPage'
import type { StudentIdentity } from '../src/types/api'

vi.mock('../src/api/students', () => ({
  studentsApi: {
    list: vi.fn(),
    provision: vi.fn(),
    update: vi.fn(),
    resetTemporaryPassword: vi.fn(),
    importRoster: vi.fn(),
    completeOnboarding: vi.fn(),
  },
}))

const student: StudentIdentity = {
  user_id: 41,
  registration_number: 'FA26-BAI-041',
  full_name: 'Provisioned Student',
  institutional_email: null,
  department: 'Computing',
  program: 'BS Artificial Intelligence',
  batch: '2026',
  current_semester: 1,
  section: 'A',
  academic_status: 'active',
  is_verified: true,
  is_active: true,
  must_change_password: true,
  preferred_name: null,
  onboarding_completed: false,
  created_at: '2026-08-29T00:00:00Z',
  updated_at: '2026-08-29T00:00:00Z',
}

describe('student management', () => {
  beforeEach(() => {
    vi.mocked(studentsApi.list).mockResolvedValue({
      students: [student],
      total: 1,
      offset: 0,
      limit: 25,
    })
    vi.mocked(studentsApi.provision).mockResolvedValue({
      student,
      temporary_password: 'temporary-secret',
    })
  })

  it('lists institutional identities and provisions a registration-login student', async () => {
    const user = userEvent.setup()
    render(<StudentsPage />)

    expect(await screen.findByText('FA26-BAI-041')).toBeInTheDocument()
    expect(screen.getByText('Registration-number login')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Provision student' }))
    const dialog = screen.getByRole('dialog', { name: 'Provision institutional student' })

    await user.type(within(dialog).getByLabelText('Registration number'), 'FA26-BAI-099')
    await user.type(within(dialog).getByLabelText('Full name'), 'New Student')
    await user.type(within(dialog).getByLabelText('Department'), 'Computing')
    await user.type(within(dialog).getByLabelText('Program'), 'BS Artificial Intelligence')
    await user.type(within(dialog).getByLabelText('Batch'), '2026')
    await user.clear(within(dialog).getByLabelText('Current semester'))
    await user.type(within(dialog).getByLabelText('Current semester'), '1')
    await user.type(within(dialog).getByLabelText('Section'), 'B')

    await user.click(within(dialog).getByRole('button', { name: 'Provision student' }))

    await waitFor(() => {
      expect(studentsApi.provision).toHaveBeenCalledWith(
        expect.objectContaining({
          registration_number: 'FA26-BAI-099',
          full_name: 'New Student',
          email: null,
          current_semester: 1,
          section: 'B',
          is_verified: true,
          is_active: true,
        }),
      )
    })

    const credential = await screen.findByRole('dialog', {
      name: 'Temporary student credential',
    })
    expect(within(credential).getByTestId('temporary-password')).toHaveTextContent(
      'temporary-secret',
    )
  })
})
