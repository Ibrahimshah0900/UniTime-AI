import { describe, expect, it } from 'vitest'
import { navForRole } from '../src/app/navigation'

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
})
