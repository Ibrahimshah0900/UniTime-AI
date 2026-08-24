import { describe, expect, it } from 'vitest'
import { groupTimetable, sortTimetable } from '../src/utils/timetable'
import type { TimetableEntry } from '../src/types/api'

function entry(id: number, day: TimetableEntry['day'], start_time: string): TimetableEntry {
  return {
    id,
    entry_kind: 'course',
    course_code: `CS${id}`,
    course_name: null,
    semester: null,
    section: 'A',
    faculty: null,
    room: null,
    day,
    start_time,
    end_time: '12:00',
    class_type: 'lecture',
    raw_text: null,
    source: 'manual',
  }
}

describe('timetable helpers', () => {
  it('orders by weekday then time', () => {
    const result = sortTimetable([entry(1, 'Tuesday', '09:00'), entry(2, 'Monday', '12:00'), entry(3, 'Monday', '08:00')])
    expect(result.map((item) => item.id)).toEqual([3, 2, 1])
  })

  it('creates every weekday bucket', () => {
    const grouped = groupTimetable([entry(1, 'Monday', '09:00')])
    expect(Object.keys(grouped)).toHaveLength(7)
    expect(grouped.Monday).toHaveLength(1)
    expect(grouped.Sunday).toHaveLength(0)
  })
})
