import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { LoginPage, RegisterPage } from '../src/pages/AuthPages'

vi.mock('../src/features/auth/AuthContext', () => ({
  useAuth: () => ({
    user: null,
    login: vi.fn(),
  }),
}))

function renderAuth(path: '/login' | '/register') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('public student registration mode', () => {
  it('defaults the institutional login experience away from self-registration', () => {
    vi.stubEnv('VITE_ALLOW_PUBLIC_STUDENT_REGISTRATION', '0')
    renderAuth('/login')

    expect(
      screen.queryByRole('link', { name: 'Create your account' }),
    ).not.toBeInTheDocument()
    expect(
      screen.getByText('Students receive sign-in credentials from the university.'),
    ).toBeInTheDocument()
  })

  it('redirects the registration route when self-registration is disabled', async () => {
    vi.stubEnv('VITE_ALLOW_PUBLIC_STUDENT_REGISTRATION', '0')
    renderAuth('/register')

    expect(
      await screen.findByRole('heading', { name: 'Welcome back' }),
    ).toBeInTheDocument()
  })

  it('keeps the explicit development registration mode available', () => {
    vi.stubEnv('VITE_ALLOW_PUBLIC_STUDENT_REGISTRATION', '1')
    renderAuth('/login')

    expect(
      screen.getByRole('link', { name: 'Create your account' }),
    ).toBeInTheDocument()
  })
})
