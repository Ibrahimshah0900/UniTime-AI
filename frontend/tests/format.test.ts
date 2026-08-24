import { describe, expect, it } from 'vitest'
import { parseBackendDate } from '../src/utils/format'

describe('backend timestamp parsing', () => {
  it('treats timezone-less backend timestamps as UTC', () => {
    expect(parseBackendDate('2026-08-25T03:55:00').toISOString()).toBe('2026-08-25T03:55:00.000Z')
  })

  it('preserves timestamps that already include a timezone', () => {
    expect(parseBackendDate('2026-08-25T08:55:00+05:00').toISOString()).toBe('2026-08-25T03:55:00.000Z')
    expect(parseBackendDate('2026-08-25T03:55:00Z').toISOString()).toBe('2026-08-25T03:55:00.000Z')
  })
})
