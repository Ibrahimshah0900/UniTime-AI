import { MapPin, UserRound } from 'lucide-react'
import type { TimetableEntry } from '../types/api'
import { classLabel, formatClock } from '../utils/format'
import { groupTimetable } from '../utils/timetable'

export function TimetableView({ entries }: { entries: TimetableEntry[] }) {
  const grouped = groupTimetable(entries)
  return <div className="timetable-grid">{Object.entries(grouped).map(([day, dayEntries]) => <section className="timetable-day" key={day}><h3>{day.slice(0, 3)}</h3><div className="timetable-day__body">{dayEntries.length ? dayEntries.map((entry) => <article className={`class-block class-block--${entry.class_type}`} key={entry.id}><div className="class-block__time">{formatClock(entry.start_time)} – {formatClock(entry.end_time)}</div><strong>{classLabel(entry)}</strong><span>{entry.course_code || 'Special event'}{entry.section ? ` · Section ${entry.section}` : ''}</span>{entry.room && <small><MapPin size={12}/>{entry.room}</small>}{entry.faculty && <small><UserRound size={12}/>{entry.faculty}</small>}</article>) : <span className="timetable-day__empty">No classes</span>}</div></section>)}</div>
}
