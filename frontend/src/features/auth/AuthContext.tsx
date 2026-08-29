import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { authApi } from '../../api/auth'
import { ApiError, clearStoredToken, getStoredToken, storeToken } from '../../api/client'
import type { User } from '../../types/api'

interface AuthContextValue {
  user: User | null
  token: string | null
  loading: boolean
  restoreError: string | null
  login: (identifier: string, password: string) => Promise<User>
  logout: () => void
  refreshUser: () => Promise<User | null>
  setUser: (user: User | null) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(() => getStoredToken())
  const [loading, setLoading] = useState(true)
  const [restoreError, setRestoreError] = useState<string | null>(null)

  const logout = useCallback(() => {
    clearStoredToken()
    setToken(null)
    setUser(null)
    setRestoreError(null)
  }, [])

  const refreshUser = useCallback(async () => {
    setLoading(true)
    setRestoreError(null)
    if (!getStoredToken()) {
      setUser(null)
      setLoading(false)
      return null
    }
    try {
      const current = await authApi.me()
      setUser(current)
      return current
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        logout()
      } else {
        const message = error instanceof ApiError || error instanceof Error
          ? error.message
          : 'Unable to restore the authenticated session.'
        setRestoreError(message)
      }
      return null
    } finally {
      setLoading(false)
    }
  }, [logout])

  useEffect(() => { void refreshUser() }, [refreshUser])
  useEffect(() => {
    const handleUnauthorized = () => logout()
    window.addEventListener('unitime:unauthorized', handleUnauthorized)
    return () => window.removeEventListener('unitime:unauthorized', handleUnauthorized)
  }, [logout])

  const login = useCallback(async (identifier: string, password: string) => {
    const response = await authApi.login(identifier, password)
    storeToken(response.access_token)
    setToken(response.access_token)
    setUser(response.user)
    setRestoreError(null)
    return response.user
  }, [])

  const value = useMemo(() => ({ user, token, loading, restoreError, login, logout, refreshUser, setUser }), [user, token, loading, restoreError, login, logout, refreshUser])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
