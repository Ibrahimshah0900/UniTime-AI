import type { DayName, TimetableEntry } from '../types/api'
import { DAY_ORDER } from './format'

export function sortTimetable(entries: TimetableEntry[]) {
  return [...entries].sort((a, b) => {
    const dayDiff = DAY_ORDER.indexOf(a.day as DayName) - DAY_ORDER.indexOf(b.day as DayName)
    if (dayDiff !== 0) return dayDiff
    return a.start_time.localeCompare(b.start_time)
  })
}

export function groupTimetable(entries: TimetableEntry[]) {
  return DAY_ORDER.reduce<Record<string, TimetableEntry[]>>((groups, day) => {
    groups[day] = sortTimetable(entries.filter((entry) => entry.day === day))
    return groups
  }, {})
}

export function nextClass(entries: TimetableEntry[]) {
  const now = new Date()
  const currentDay = new Intl.DateTimeFormat('en-US', { weekday: 'long' }).format(now)
  const minutes = now.getHours() * 60 + now.getMinutes()
  const today = sortTimetable(entries.filter((entry) => entry.day === currentDay))
  return today.find((entry) => {
    const [hours, mins] = entry.start_time.split(':').map(Number)
    return hours * 60 + mins >= minutes
  }) || today[0] || sortTimetable(entries)[0] || null
}
