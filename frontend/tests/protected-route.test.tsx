import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ProtectedRoute } from '../src/routes/ProtectedRoute'
import type { User } from '../src/types/api'

const auth = vi.hoisted(() => ({
  value: { user: null as Pick<User, 'role'> | null, loading: false },
}))
vi.mock('../src/features/auth/AuthContext', () => ({ useAuth: () => auth.value }))

describe('ProtectedRoute', () => {
  beforeEach(() => { auth.value = { user: null, loading: false } })

  it('renders allowed content for an authorized role', () => {
    auth.value = { user: { role: 'student' }, loading: false }
    render(<MemoryRouter><ProtectedRoute roles={['student']}><div>Student content</div></ProtectedRoute></MemoryRouter>)
    expect(screen.getByText('Student content')).toBeInTheDocument()
  })

  it('does not render content for a different role', () => {
    auth.value = { user: { role: 'faculty' }, loading: false }
    render(<MemoryRouter><ProtectedRoute roles={['student']}><div>Student content</div></ProtectedRoute></MemoryRouter>)
    expect(screen.queryByText('Student content')).not.toBeInTheDocument()
  })
})
