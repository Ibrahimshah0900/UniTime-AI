import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { ErrorState, LoadingState } from '../components/Ui'
import { useAuth } from '../features/auth/AuthContext'
import type { UserRole } from '../types/api'

export function ProtectedRoute({ children, roles }: { children: ReactNode; roles?: UserRole[] }) {
  const { user, token, loading, restoreError, refreshUser } = useAuth()
  const location = useLocation()
  if (loading) return <LoadingState label="Restoring your session"/>
  if (!user && token && restoreError) return <div className="center-page"><ErrorState message={restoreError} retry={() => { void refreshUser() }}/></div>
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }}/>
  const studentOnboardingRequired = Boolean(
    user.role === 'student' &&
    user.student_profile &&
    !user.student_profile.onboarding_completed,
  )
  if ((user.must_change_password || studentOnboardingRequired) && location.pathname !== '/account') {
    return <Navigate to="/account" replace/>
  }
  if (roles && !roles.includes(user.role)) return <Navigate to="/forbidden" replace/>
  return <>{children}</>
}
