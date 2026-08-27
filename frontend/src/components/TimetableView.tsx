import { Clock3, MapPin, UserRound } from 'lucide-react'
import { motion } from 'motion/react'
import type { TimetableEntry } from '../types/api'
import { classLabel, formatClock } from '../utils/format'
import { groupTimetable } from '../utils/timetable'

function classTypeLabel(value: TimetableEntry['class_type']) {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

export function TimetableView({ entries }: { entries: TimetableEntry[] }) {
  const grouped = groupTimetable(entries)
  const today = new Intl.DateTimeFormat('en-US', { weekday: 'long' }).format(new Date())

  return <section className="timetable-board" aria-label="Weekly timetable">
    <header className="timetable-board__header">
      <div>
        <span className="eyebrow">Weekly schedule</span>
        <strong>{entries.length} scheduled {entries.length === 1 ? 'item' : 'items'}</strong>
      </div>
      <span className="timetable-board__legend">Scroll horizontally to explore the full week</span>
    </header>

    <div className="timetable-grid">
      {Object.entries(grouped).map(([day, dayEntries], dayIndex) => {
        const isToday = day === today

        return <motion.section
          className={`timetable-day ${isToday ? 'timetable-day--today' : ''}`}
          key={day}
          aria-label={`${day} schedule`}
          aria-current={isToday ? 'date' : undefined}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            duration: 0.28,
            delay: dayIndex * 0.025,
            ease: [0.22, 1, 0.36, 1],
          }}
        >
          <header className="timetable-day__header">
            <div>
              <span>{day.slice(0, 3)}</span>
              <strong>{day}</strong>
            </div>

            <div className="timetable-day__badges">
              {isToday && <span className="timetable-today">Today</span>}
              <span className="timetable-count">
                {dayEntries.length} {dayEntries.length === 1 ? 'class' : 'classes'}
              </span>
            </div>
          </header>

          <div className="timetable-day__body">
            {dayEntries.length
              ? dayEntries.map((entry, entryIndex) => (
                  <motion.article
                    className={`class-block class-block--${entry.class_type}`}
                    key={entry.id}
                    initial={{ opacity: 0, scale: 0.98 }}
                    animate={{ opacity: 1, scale: 1 }}
                    whileHover={{ y: -3 }}
                    transition={{
                      duration: 0.22,
                      delay: dayIndex * 0.025 + entryIndex * 0.025,
                      ease: [0.22, 1, 0.36, 1],
                    }}
                  >
                    <div className="class-block__top">
                      <span className="class-block__type">
                        {entry.entry_kind === 'special_event'
                          ? 'Event'
                          : classTypeLabel(entry.class_type)}
                      </span>

                      <span className="class-block__time">
                        <Clock3 size={12}/>
                        {formatClock(entry.start_time)} - {formatClock(entry.end_time)}
                      </span>
                    </div>

                    <strong>{classLabel(entry)}</strong>

                    {(entry.course_code || entry.section) && (
                      <div className="class-block__identity">
                        {entry.course_code && <span>{entry.course_code}</span>}
                        {entry.section && <span>Section {entry.section}</span>}
                      </div>
                    )}

                    {(entry.room || entry.faculty) && (
                      <div className="class-block__meta">
                        {entry.room && (
                          <small>
                            <MapPin size={12}/>
                            {entry.room}
                          </small>
                        )}

                        {entry.faculty && (
                          <small>
                            <UserRound size={12}/>
                            {entry.faculty}
                          </small>
                        )}
                      </div>
                    )}
                  </motion.article>
                ))
              : <div className="timetable-day__empty">
                  <span/>
                  <strong>Open day</strong>
                  <small>No scheduled classes</small>
                </div>}
          </div>
        </motion.section>
      })}
    </div>
  </section>
}
