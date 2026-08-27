import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ClashesPage } from '../src/pages/OperationsPages'

const mocks = vi.hoisted(() => ({
  terms: vi.fn(),
  clashes: vi.fn(),
  rooms: vi.fn(),
  risk: vi.fn(),
  groups: vi.fn(),
  resolutions: vi.fn(),
  applyRoomFix: vi.fn(),
  applyGroupFix: vi.fn(),
}))

vi.mock('../src/api/terms', () => ({
  termsApi: {
    list: mocks.terms,
  },
}))

vi.mock('../src/api/operations', () => ({
  clashesApi: {
    all: mocks.clashes,
    roomSuggestions: mocks.rooms,
    studentRisk: mocks.risk,
    studentGroups: mocks.groups,
    studentResolutions: mocks.resolutions,
    applyRoomFix: mocks.applyRoomFix,
    applyStudentGroupFix: mocks.applyGroupFix,
  },
  historyApi: {},
  optimizerApi: {},
}))

const firstEntry = {
  id: 10,
  course_code: 'AI-301',
  course_name: 'Artificial Intelligence',
  semester: 'Fall 2026',
  section: 'A',
  faculty: 'Dr Sara',
  room: 'LAB-1',
  start_time: '09:00',
  end_time: '10:00',
}

const secondEntry = {
  id: 11,
  course_code: 'MTH-201',
  course_name: 'Discrete Mathematics',
  semester: 'Fall 2026',
  section: 'A',
  faculty: 'Dr Ali',
  room: 'LAB-1',
  start_time: '09:30',
  end_time: '10:30',
}

describe('Clash Management Experience v2', () => {
  beforeEach(() => {
    mocks.terms.mockReset().mockResolvedValue({
      terms: [{
        id: 1,
        code: 'FALL-2026',
        name: 'Fall 2026',
        status: 'active',
        starts_on: '2026-08-01',
        ends_on: '2026-12-31',
        created_by_user_id: 1,
        activated_at: '2026-08-01T00:00:00',
        archived_at: null,
        created_at: '2026-08-01T00:00:00',
        updated_at: '2026-08-01T00:00:00',
      }],
      total: 1,
      active_term_id: 1,
    })

    mocks.clashes.mockReset().mockResolvedValue({
      total: 1,
      clashes: [{
        type: 'room',
        severity: 'critical',
        day: 'Monday',
        overlap: {
          entry_1_time: '09:00-10:00',
          entry_2_time: '09:30-10:30',
        },
        reason: 'Both classes use LAB-1 during an overlapping period.',
        entry_1: firstEntry,
        entry_2: secondEntry,
      }],
    })

    mocks.rooms.mockReset().mockResolvedValue({
      room_clashes: 1,
      resolutions: [{
        clash_type: 'room',
        day: 'Monday',
        reason: 'LAB-1 is double-booked.',
        best_fix: {
          entry_id: 10,
          course_code: 'AI-301',
          course_name: 'Artificial Intelligence',
          from_room: 'LAB-1',
          to_room: 'LAB-2',
          day: 'Monday',
          start_time: '09:00',
          end_time: '10:00',
          score: 95,
          weekly_usage_count: 2,
          reasons: [
            'No room overlap',
            'Class duration preserved',
          ],
        },
        suggestions: [],
      }],
    })

    mocks.risk.mockReset().mockResolvedValue({
      summary: {
        total: 1,
        confirmed: 1,
        probable: 0,
        possible: 0,
        enrollment_backed: 1,
        inferred: 0,
        enrollment_records: 20,
        verified_students: 12,
        unmapped_enrollment_records: 0,
        important_note: 'Enrollment evidence is available for this conflict.',
      },
      risks: [{
        type: 'student',
        risk_type: 'course_overlap',
        risk_level: 'confirmed',
        score: 88,
        day: 'Monday',
        overlap: {
          entry_1_time: '09:00-10:00',
          entry_2_time: '09:30-10:30',
        },
        shared_sections: ['A'],
        same_course_level: true,
        evidence_source: 'enrollment',
        affected_student_count: 12,
        enrollment_coverage: 'complete_for_edge',
        evidence: ['12 verified shared students'],
        limitations: [],
        entry_1: firstEntry,
        entry_2: secondEntry,
      }],
    })

    mocks.groups.mockReset().mockResolvedValue({
      summary: {
        total_groups: 1,
        confirmed_groups: 1,
        probable_groups: 0,
        enrollment_backed_groups: 1,
        unique_timetable_entries_involved: 2,
        important_note: 'Groups combine related student conflict edges.',
      },
      groups: [{
        group_id: 7,
        type: 'student_conflict',
        risk_level: 'confirmed',
        priority_score: 90,
        day: 'Monday',
        time_window: {
          start_time: '09:00',
          end_time: '10:30',
        },
        course_levels: [200, 300],
        shared_sections: ['A'],
        courses_involved: 2,
        pairwise_risks: 1,
        entries: [firstEntry, secondEntry],
        evidence: ['Verified enrollment overlap'],
        limitations: [],
        evidence_sources: ['enrollment'],
        enrollment_backed_edges: 1,
        action: 'Review validated alternatives.',
      }],
    })

    mocks.resolutions.mockReset().mockResolvedValue({
      summary: {
        total_groups: 1,
        groups_with_suggestion: 1,
        groups_without_suggestion: 0,
        fully_feasible_best_fixes: 1,
        best_fixes_requiring_room: 0,
        important_note: 'Only validated candidates are returned.',
      },
      resolutions: [{
        group_id: 7,
        risk_level: 'confirmed',
        priority_score: 90,
        day: 'Monday',
        time_window: {
          start_time: '09:00',
          end_time: '10:30',
        },
        courses_involved: 2,
        best_fix: {
          entry_id: 10,
          course_code: 'AI-301',
          course_name: 'Artificial Intelligence',
          section: 'A',
          faculty: 'Dr Sara',
          current_room: 'LAB-1',
          class_type: 'lecture',
          move_from: {
            day: 'Monday',
            start_time: '09:00',
            end_time: '10:00',
          },
          move_to: {
            day: 'Tuesday',
            start_time: '11:00',
            end_time: '12:00',
          },
          score: 91,
          faculty_available: true,
          room_status: 'available',
          room_available: true,
          risk_before: {},
          risk_after: {},
          risk_cost_before: 10,
          risk_cost_after: 0,
          reasons: ['Removes confirmed overlap'],
        },
        alternatives: [],
        important_note: 'Validated candidate.',
      }],
    })

    mocks.applyRoomFix.mockReset()
    mocks.applyGroupFix.mockReset()
  })

  it('presents conflicts, evidence, and validated actions clearly', async () => {
    render(<ClashesPage/>)

    await waitFor(() => {
      expect(mocks.clashes).toHaveBeenCalledWith(1)
    })

    expect(
      await screen.findByRole('heading', { name: 'Clash management' }),
    ).toBeInTheDocument()

    expect(
      screen.getByRole('heading', { name: 'Detected structural clashes' }),
    ).toBeInTheDocument()

    const structuralHeading = screen.getByRole(
      'heading',
      { name: 'Detected structural clashes' },
    )
    const structuralSection = structuralHeading.closest('section')

    expect(structuralSection).not.toBeNull()

    if (!structuralSection) {
      throw new Error('Structural clashes section was not rendered.')
    }

    const coursePair = structuralSection.querySelector('.clash-card__courses')

    expect(coursePair).not.toBeNull()
    expect(coursePair).toHaveTextContent('AI-301')
    expect(coursePair).toHaveTextContent('MTH-201')

    expect(
      screen.getByText('Room conflict'),
    ).toBeInTheDocument()

    expect(
      screen.getByText('Affected students'),
    ).toBeInTheDocument()

    expect(
      screen.getByText('12 verified shared students'),
    ).toBeInTheDocument()

    expect(
      screen.getByRole('button', { name: 'Apply fix' }),
    ).toBeEnabled()

    expect(
      screen.getByText('Live resolution mode'),
    ).toBeInTheDocument()
  })
})
