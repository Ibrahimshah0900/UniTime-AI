import { describe, expect, it } from 'vitest'
import { mobileStudentNav, navForRole } from '../src/app/navigation'

describe('role-aware navigation', () => {
  it('keeps admin user management admin-only', () => {
    expect(navForRole('admin').some((item) => item.path === '/admin/users')).toBe(true)
    expect(navForRole('coordinator').some((item) => item.path === '/admin/users')).toBe(false)
    expect(navForRole('faculty').some((item) => item.path === '/admin/users')).toBe(false)
    expect(navForRole('student').some((item) => item.path === '/admin/users')).toBe(false)
  })

  it('shows student-specific enrollment and clash-report navigation', () => {
    const paths = navForRole('student').map((item) => item.path)
    expect(paths).toContain('/enrollments')
    expect(paths).toContain('/clash-reports')
    expect(paths).not.toContain('/optimizer')
  })
  it('exposes institutional scheduling to coordinator/admin and true availability to faculty', () => {
    expect(navForRole('coordinator').some((item) => item.path === '/scheduling')).toBe(true)
    expect(navForRole('admin').some((item) => item.path === '/scheduling')).toBe(true)
    expect(navForRole('faculty').some((item) => item.path === '/scheduling')).toBe(false)
    expect(navForRole('student').some((item) => item.path === '/scheduling')).toBe(false)
    expect(navForRole('faculty').some((item) => item.path === '/faculty-availability')).toBe(true)
    expect(navForRole('coordinator').some((item) => item.path === '/faculty-availability')).toBe(false)
  })

  it('exposes quality and resolver analytics only to coordinator/admin roles', () => {
    expect(navForRole('coordinator').some((item) => item.path === '/insights')).toBe(true)
    expect(navForRole('admin').some((item) => item.path === '/insights')).toBe(true)
    expect(navForRole('faculty').some((item) => item.path === '/insights')).toBe(false)
    expect(navForRole('student').some((item) => item.path === '/insights')).toBe(false)
  })


  it(`keeps student mobile navigation complete`, () => {
    const paths = mobileStudentNav.map((item) => item.path)
    expect(paths).toContain(`/enrollments`)
    expect(paths).toContain(`/account`)
  })
})
