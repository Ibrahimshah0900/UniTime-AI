import { formatDistanceToNow, parseISO } from 'date-fns'
import type { ClashReportStatus, TimetableEntry, UserRole } from '../types/api'

export const DAY_ORDER = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'] as const

export function titleCase(value: string) {
  return value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

export function parseBackendDate(value: string) {
  const normalized = value.trim()

  // Backend timestamps are UTC. SQLite may serialize them without
  // an explicit timezone, so add Z only when no timezone is present.
  const hasTimezone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(normalized)

  return parseISO(hasTimezone ? normalized : `${normalized}Z`)
}

export function formatRelative(value: string) {
  try {
    return formatDistanceToNow(parseBackendDate(value), { addSuffix: true })
  } catch {
    return value
  }
}

export function formatClock(value: string | null | undefined) {
  if (!value) return '—'
  const [hoursRaw, minutes = '00'] = value.split(':')
  const hours = Number(hoursRaw)
  if (Number.isNaN(hours)) return value
  const suffix = hours >= 12 ? 'PM' : 'AM'
  const normalized = hours % 12 || 12
  return `${normalized}:${minutes.slice(0, 2)} ${suffix}`
}

export function statusTone(status: ClashReportStatus | string) {
  if (status === 'resolved') return 'success'
  if (status === 'rejected') return 'danger'
  if (status === 'under_review') return 'warning'
  if (status === 'duplicate') return 'neutral'
  return 'info'
}

export function roleLabel(role: UserRole) {
  return role === 'admin' ? 'Administrator' : titleCase(role)
}

export function classLabel(entry: TimetableEntry) {
  return entry.course_name || entry.course_code || 'Scheduled session'
}

export function isToday(day: string) {
  return new Intl.DateTimeFormat('en-US', { weekday: 'long' }).format(new Date()) === day
}

export function primitiveEntries(data: Record<string, unknown>) {
  return Object.entries(data).filter(([, value]) => ['string', 'number', 'boolean'].includes(typeof value)).slice(0, 6)
}

export function dashboardMetricEntries(data: Record<string, unknown>) {
  const entries: Array<[string, string | number | boolean]> = []
  for (const [key, value] of Object.entries(data)) {
    if (['string', 'number', 'boolean'].includes(typeof value)) {
      entries.push([key, value as string | number | boolean])
      continue
    }
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      for (const [nestedKey, nestedValue] of Object.entries(value)) {
        if (['string', 'number', 'boolean'].includes(typeof nestedValue)) {
          entries.push([`${key} · ${nestedKey}`, nestedValue as string | number | boolean])
        }
      }
    }
  }
  return entries.slice(0, 8)
}
