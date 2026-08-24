import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, clearStoredToken, getStoredToken, storeToken } from '../src/api/client'
import { AuthProvider, useAuth } from '../src/features/auth/AuthContext'

const authApiMock = vi.hoisted(() => ({ me: vi.fn() }))

vi.mock('../src/api/auth', () => ({
  authApi: {
    me: authApiMock.me,
    login: vi.fn(),
  },
}))

function Probe() {
  const { loading, restoreError, token, user } = useAuth()
  return <div>
    <span data-testid="loading">{String(loading)}</span>
    <span data-testid="token">{token || 'none'}</span>
    <span data-testid="user">{user?.email || 'none'}</span>
    <span data-testid="error">{restoreError || 'none'}</span>
  </div>
}

describe('AuthProvider session restoration', () => {
  beforeEach(() => {
    authApiMock.me.mockReset()
    clearStoredToken()
  })

  it('clears an invalid session after a real 401', async () => {
    storeToken('expired-token')
    authApiMock.me.mockRejectedValue(new ApiError('Invalid token.', 401))
    render(<AuthProvider><Probe/></AuthProvider>)

    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))
    expect(getStoredToken()).toBeNull()
    expect(screen.getByTestId('token')).toHaveTextContent('none')
    expect(screen.getByTestId('error')).toHaveTextContent('none')
  })

  it('preserves the token and exposes a retryable error on a transient failure', async () => {
    storeToken('valid-session-token')
    authApiMock.me.mockRejectedValue(new ApiError('Backend temporarily unavailable.', 503))
    render(<AuthProvider><Probe/></AuthProvider>)

    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))
    expect(getStoredToken()).toBe('valid-session-token')
    expect(screen.getByTestId('token')).toHaveTextContent('valid-session-token')
    expect(screen.getByTestId('user')).toHaveTextContent('none')
    expect(screen.getByTestId('error')).toHaveTextContent('Backend temporarily unavailable.')
  })
})
