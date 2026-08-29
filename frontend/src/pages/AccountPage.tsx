import { KeyRound, UserRound } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { authApi } from '../api/auth'
import { ApiError } from '../api/client'
import { studentsApi } from '../api/students'
import { Field, Input } from '../components/Form'
import {
  ErrorNote,
  PageHeader,
  Section,
  StatusBadge,
  SuccessNote,
} from '../components/Ui'
import { useAuth } from '../features/auth/AuthContext'
import { roleLabel, titleCase } from '../utils/format'

export function AccountPage() {
  const { user, setUser, logout } = useAuth()
  const [name, setName] = useState(user?.full_name || '')
  const [profileMessage, setProfileMessage] = useState('')
  const [profileError, setProfileError] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [passwordMessage, setPasswordMessage] = useState('')
  const [passwordError, setPasswordError] = useState('')
  const [preferredName, setPreferredName] = useState(
    user?.student_profile?.preferred_name || '',
  )
  const [onboardingMessage, setOnboardingMessage] = useState('')
  const [onboardingError, setOnboardingError] = useState('')
  const [profileBusy, setProfileBusy] = useState(false)
  const [passwordBusy, setPasswordBusy] = useState(false)
  const [onboardingBusy, setOnboardingBusy] = useState(false)

  if (!user) return null

  const institutionalProfile =
    user.role === 'student' ? user.student_profile || null : null

  async function updateProfile(event: FormEvent) {
    event.preventDefault()
    if (profileBusy) return
    setProfileBusy(true)
    setProfileError('')
    setProfileMessage('')
    try {
      const updated = await authApi.updateProfile(name)
      setUser(updated)
      setProfileMessage('Profile updated.')
    } catch (err) {
      setProfileError(err instanceof ApiError ? err.message : 'Unable to update profile.')
    } finally {
      setProfileBusy(false)
    }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault()
    if (passwordBusy) return
    setPasswordBusy(true)
    setPasswordError('')
    setPasswordMessage('')
    try {
      await authApi.changePassword(currentPassword, newPassword)
      setCurrentPassword('')
      setNewPassword('')
      setPasswordMessage(
        'Password changed. Existing access tokens are invalidated; please sign in again.',
      )
      setTimeout(logout, 900)
    } catch (err) {
      setPasswordError(err instanceof ApiError ? err.message : 'Unable to change password.')
      setPasswordBusy(false)
    }
  }

  async function completeOnboarding(event: FormEvent) {
    event.preventDefault()
    if (onboardingBusy || !user || user.must_change_password) return
    setOnboardingBusy(true)
    setOnboardingError('')
    setOnboardingMessage('')
    try {
      const completed = await studentsApi.completeOnboarding(preferredName.trim() || null)
      setUser({
        ...user,
        must_change_password: completed.must_change_password,
        student_profile: {
          registration_number: completed.registration_number,
          department: completed.department,
          program: completed.program,
          batch: completed.batch,
          current_semester: completed.current_semester,
          section: completed.section,
          academic_status: completed.academic_status,
          is_verified: completed.is_verified,
          preferred_name: completed.preferred_name,
          onboarding_completed: completed.onboarding_completed,
        },
      })
      setOnboardingMessage('Student onboarding completed.')
    } catch (err) {
      setOnboardingError(
        err instanceof ApiError ? err.message : 'Unable to complete student onboarding.',
      )
    } finally {
      setOnboardingBusy(false)
    }
  }

  return (
    <div className="page">
      <PageHeader
        title="Account"
        description="Manage the profile and password attached to your authenticated UniTime-AI account."
      />

      {user.must_change_password && (
        <div className="soft-panel">
          <strong>First sign-in: change your temporary password</strong>
          <p>
            Your account is intentionally restricted until the temporary password is
            replaced. Change it below, then sign in again to continue onboarding.
          </p>
        </div>
      )}

      {onboardingMessage && <SuccessNote>{onboardingMessage}</SuccessNote>}

      <div className="two-column">
        <Section
          title={institutionalProfile ? 'Institutional student identity' : 'Profile'}
          description={
            institutionalProfile
              ? 'Official student identity fields are managed by a coordinator or administrator.'
              : 'Your role and email are controlled by the backend account system.'
          }
        >
          <div className="profile-summary">
            <div className="profile-summary__avatar">{user.full_name.slice(0, 1)}</div>
            <div>
              <strong>{user.full_name}</strong>
              <span>
                {user.email ||
                  institutionalProfile?.registration_number ||
                  'No institutional email assigned'}
              </span>
              <StatusBadge tone="info">{roleLabel(user.role)}</StatusBadge>
            </div>
          </div>

          {institutionalProfile ? (
            <div className="report-strip">
              <article><div><strong>Registration</strong><span>{institutionalProfile.registration_number}</span></div></article>
              <article><div><strong>Program</strong><span>{institutionalProfile.program}</span></div></article>
              <article><div><strong>Department</strong><span>{institutionalProfile.department}</span></div></article>
              <article><div><strong>Batch / semester / section</strong><span>{institutionalProfile.batch} · Semester {institutionalProfile.current_semester} · Section {institutionalProfile.section}</span></div></article>
              <article><div><strong>Academic status</strong><span>{titleCase(institutionalProfile.academic_status)}</span></div></article>
              <article><div><strong>Verification</strong><span>{institutionalProfile.is_verified ? 'Verified' : 'Not verified'}</span></div></article>
            </div>
          ) : (
            <form className="form-stack" onSubmit={updateProfile}>
              <Field label="Full name">
                <Input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  minLength={2}
                  maxLength={200}
                  required
                />
              </Field>
              {profileError && <ErrorNote>{profileError}</ErrorNote>}
              {profileMessage && <SuccessNote>{profileMessage}</SuccessNote>}
              <button className="btn btn--primary" disabled={profileBusy}>
                <UserRound size={16} />
                {profileBusy ? 'Saving…' : 'Save profile'}
              </button>
            </form>
          )}
        </Section>

        <Section
          title="Change password"
          description={
            user.must_change_password
              ? 'Replace the one-time password before using protected UniTime-AI features.'
              : 'Changing your password invalidates previously issued access tokens.'
          }
        >
          <form className="form-stack" onSubmit={changePassword}>
            <Field label="Current password">
              <Input
                type="password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                required
              />
            </Field>
            <Field label="New password" hint="8–128 characters">
              <Input
                type="password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                minLength={8}
                maxLength={128}
                required
              />
            </Field>
            {passwordError && <ErrorNote>{passwordError}</ErrorNote>}
            {passwordMessage && <SuccessNote>{passwordMessage}</SuccessNote>}
            <button className="btn btn--secondary" disabled={passwordBusy}>
              <KeyRound size={16} />
              {passwordBusy ? 'Changing…' : 'Change password'}
            </button>
          </form>
        </Section>
      </div>

      {institutionalProfile && !institutionalProfile.onboarding_completed && (
        <Section
          title="Finish student onboarding"
          description="Confirm your preferred display name after changing the temporary password."
        >
          {user.must_change_password ? (
            <div className="soft-panel">
              Change the temporary password above first. You can complete onboarding after
              signing in again with the new password.
            </div>
          ) : (
            <form className="form-stack" onSubmit={completeOnboarding}>
              <Field label="Preferred name" hint="Optional. Your official university name is not changed.">
                <Input
                  value={preferredName}
                  onChange={(event) => setPreferredName(event.target.value)}
                  maxLength={100}
                />
              </Field>
              {onboardingError && <ErrorNote>{onboardingError}</ErrorNote>}
              <button className="btn btn--primary" disabled={onboardingBusy}>
                {onboardingBusy ? 'Completing…' : 'Complete onboarding'}
              </button>
            </form>
          )}
        </Section>
      )}
    </div>
  )
}
