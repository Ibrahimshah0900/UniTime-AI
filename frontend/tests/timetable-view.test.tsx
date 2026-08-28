import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { TimetableView } from '../src/components/TimetableView'
import type { TimetableEntry } from '../src/types/api'

const entry: TimetableEntry = {
  id: 1,
  term_id: 1,
  entry_kind: 'course',
  course_code: 'CS-210',
  course_name: 'Data Structures',
  semester: 'Fall 2026',
  section: 'A',
  faculty: 'Dr. Sara',
  room: 'CS-301',
  day: 'Monday',
  start_time: '09:00',
  end_time: '10:00',
  class_type: 'lecture',
  raw_text: null,
  source: 'manual',
}

describe('TimetableView', () => {
  it('renders the weekly timetable with rich class metadata', () => {
    render(<TimetableView entries={[entry]}/>)

    expect(screen.getByLabelText('Weekly timetable')).toBeVisible()
    expect(screen.queryByText('7 scheduled items')).not.toBeInTheDocument()
    expect(screen.getByText('1 scheduled item')).toBeVisible()

    expect(screen.getByText('Data Structures')).toBeInTheDocument()
    expect(screen.getByText('CS-210')).toBeInTheDocument()
    expect(screen.getByText('Section A')).toBeInTheDocument()
    expect(screen.getByText('Lecture')).toBeInTheDocument()
    expect(screen.getByText('CS-301')).toBeInTheDocument()
    expect(screen.getByText('Dr. Sara')).toBeInTheDocument()

    expect(screen.getByLabelText('Monday schedule')).toBeInTheDocument()
    expect(screen.getByText('1 class')).toBeInTheDocument()
    expect(screen.getAllByText('No scheduled classes').length).toBeGreaterThan(0)
  })

  it('marks deterministic generated sessions in the weekly view', () => {
    const generated: TimetableEntry = {
      ...entry,
      id: 2,
      day: 'Tuesday',
      source: 'generated',
    }

    render(<TimetableView entries={[generated]}/>)

    expect(screen.getByText('Lecture · Generated')).toBeInTheDocument()
    expect(screen.getByText('Data Structures')).toBeInTheDocument()
  })
})
