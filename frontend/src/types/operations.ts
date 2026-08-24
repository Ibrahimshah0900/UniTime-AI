export interface TimeSlot {
  day: string
  start_time: string
  end_time: string
}

export interface ClashEntry {
  id: number
  entry_kind?: string | null
  course_code: string | null
  course_name: string | null
  semester: string | null
  section: string | null
  faculty: string | null
  room: string | null
  day?: string | null
  start_time: string
  end_time: string
  class_type?: string | null
  course_levels?: number[]
  raw_text?: string | null
}

export interface StructuralClash {
  type: string
  severity: string
  day: string
  overlap: {
    entry_1_time: string
    entry_2_time: string
  }
  reason: string
  entry_1: ClashEntry
  entry_2: ClashEntry
}

export interface ClashCollection {
  total: number
  clashes: StructuralClash[]
}

export interface RoomFix {
  entry_id: number
  course_code: string | null
  course_name: string | null
  from_room: string | null
  to_room: string
  day: string
  start_time: string
  end_time: string
  score: number
  weekly_usage_count: number
  reasons: string[]
}

export interface RoomResolution {
  clash_type: string
  day: string
  reason: string
  best_fix: RoomFix | null
  suggestions: Array<{
    entry_id: number
    course_code: string | null
    course_name: string | null
    current_room: string | null
    day: string
    start_time: string
    end_time: string
    class_type: string
    alternative_rooms: Array<{
      room: string
      room_type: string
      weekly_usage_count: number
      score: number
      reasons: string[]
    }>
  }>
  error?: string
}

export interface RoomSuggestionCollection {
  room_clashes: number
  resolutions: RoomResolution[]
}

export interface StudentRisk {
  type: string
  risk_type: string
  risk_level: string
  score: number
  day: string
  overlap: {
    entry_1_time: string
    entry_2_time: string
  }
  shared_sections: string[]
  same_course_level: boolean
  evidence: string[]
  limitations: string[]
  entry_1: ClashEntry
  entry_2: ClashEntry
}

export interface StudentRiskCollection {
  summary: {
    total: number
    confirmed: number
    probable: number
    possible: number
    important_note: string
  }
  risks: StudentRisk[]
}

export interface StudentConflictGroup {
  group_id: number
  type: string
  risk_level: string
  priority_score: number
  day: string
  time_window: {
    start_time: string
    end_time: string
  }
  course_levels: number[]
  shared_sections: string[]
  courses_involved: number
  pairwise_risks: number
  entries: ClashEntry[]
  evidence: string[]
  limitations: string[]
  action: string
}

export interface StudentGroupCollection {
  summary: {
    total_groups: number
    confirmed_groups: number
    probable_groups: number
    unique_timetable_entries_involved: number
    important_note: string
  }
  groups: StudentConflictGroup[]
}

export interface StudentMove {
  entry_id: number
  course_code: string | null
  course_name: string | null
  section: string | null
  faculty: string | null
  current_room: string | null
  class_type: string
  move_from: TimeSlot
  move_to: TimeSlot
  score: number
  faculty_available: boolean
  room_status: string
  room_available: boolean | null
  risk_before: Record<string, number>
  risk_after: Record<string, number>
  risk_cost_before: number
  risk_cost_after: number
  reasons: string[]
}

export interface StudentResolution {
  group_id: number
  risk_level: string
  priority_score: number
  day: string
  time_window: { start_time: string; end_time: string }
  courses_involved: number
  best_fix: StudentMove | null
  alternatives: StudentMove[]
  important_note: string
}

export interface StudentResolutionCollection {
  summary: {
    total_groups: number
    groups_with_suggestion: number
    groups_without_suggestion: number
    fully_feasible_best_fixes: number
    best_fixes_requiring_room: number
    important_note: string
  }
  resolutions: StudentResolution[]
}

export interface OptimizerImprovementValue {
  before: number
  after: number
  reduction: number
}

export interface OptimizerMove {
  source_group_id: number
  entry_id: number
  course_code: string | null
  course_name: string | null
  section: string | null
  faculty: string | null
  room: string | null
  class_type: string
  move_from: TimeSlot
  move_to: TimeSlot
  local_score: number
  global_score: number
  room_status: string
  improvement: {
    student_risk_cost: OptimizerImprovementValue
    student_risks: OptimizerImprovementValue
    student_groups: OptimizerImprovementValue
    general_clashes: OptimizerImprovementValue
  }
  reasons: string[]
}

export interface OptimizerSnapshot {
  student_risk_cost: number
  student_risks: Record<string, number>
  student_groups: number
  clashes: Record<string, number>
}

export interface GlobalOptimization {
  baseline: OptimizerSnapshot
  candidate_summary: {
    generated: number
    globally_safe: number
    rejected: number
  }
  best_move: OptimizerMove | null
  ranked_moves: OptimizerMove[]
  important_note: string
}

export interface OptimizerPlanStep extends OptimizerMove {
  step: number
}

export interface OptimizerPlan {
  requested_max_steps: number
  planned_steps: number
  stop_reason: string
  baseline: OptimizerSnapshot
  projected_final: OptimizerSnapshot
  overall_improvement: {
    student_risk_cost: OptimizerImprovementValue
    student_risks: OptimizerImprovementValue
    student_groups: OptimizerImprovementValue
    general_clashes: OptimizerImprovementValue
  }
  planner_statistics: {
    unique_entries_moved: number
    rejected_during_planning: number
  }
  steps: OptimizerPlanStep[]
  important_note: string
}

export interface OptimizerExecution {
  execution_id: string
  status: string
  requested_steps: number
  applied_steps: number
  baseline: {
    student_risk_cost: number
    total_student_risks: number
    student_groups: number
    general_clashes: number
  }
  final: {
    student_risk_cost: number
    total_student_risks: number
    student_groups: number
    general_clashes: number
  }
  stop_reason: string | null
  error_message: string | null
  created_at: string | null
  completed_at: string | null
  steps?: Array<{ step_number: number; change_id: number }>
}

export interface OptimizerExecutionCollection {
  executions: OptimizerExecution[]
}

export interface TimetableChange {
  id: number
  entry_id: number
  change_type: string
  old_room: string | null
  new_room: string | null
  old_day: string | null
  new_day: string | null
  old_start_time: string | null
  new_start_time: string | null
  old_end_time: string | null
  new_end_time: string | null
  reason: string | null
  score: number | null
  created_at: string | null
  undone: boolean
}

export interface TimetableChangeCollection {
  total: number
  changes: TimetableChange[]
}

export interface StudentScheduleChange {
  id: number
  entry_id: number
  group_id: number
  change_type: string
  old_day: string
  old_start_time: string
  old_end_time: string
  new_day: string
  new_start_time: string
  new_end_time: string
  score: number
  risk_cost_before: number
  risk_cost_after: number
  total_risks_before: number
  total_risks_after: number
  undone: boolean
  created_at: string | null
}

export interface StudentScheduleChangeCollection {
  total: number
  changes: StudentScheduleChange[]
}

export interface AuditItem {
  audit_type: string
  history_id: number
  entry_id: number
  course_code: string | null
  course_name: string | null
  group_id?: number
  change_type: string
  before: { room?: string | null; day?: string | null; start_time?: string | null; end_time?: string | null }
  after: { room?: string | null; day?: string | null; start_time?: string | null; end_time?: string | null }
  reason?: string | null
  risk_cost_before?: number
  risk_cost_after?: number
  score: number | null
  undone: boolean
  created_at: string | null
}

export interface AuditTrail {
  summary: {
    total_changes: number
    active_changes: number
    undone_changes: number
    room_changes: number
    timetable_time_changes: number
    student_schedule_changes: number
  }
  audit_trail: AuditItem[]
}
