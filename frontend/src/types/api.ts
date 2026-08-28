export type UserRole = 'student' | 'faculty' | 'coordinator' | 'admin'

export type AcademicTermStatus = 'planning' | 'active' | 'archived'

export interface AcademicTerm {
  id: number
  code: string
  name: string
  status: AcademicTermStatus
  starts_on: string | null
  ends_on: string | null
  created_by_user_id: number | null
  activated_at: string | null
  archived_at: string | null
  created_at: string
  updated_at: string
}

export interface AcademicTermListResponse {
  terms: AcademicTerm[]
  total: number
  active_term_id: number | null
}

export interface User {
  id: number
  email: string
  full_name: string
  role: UserRole
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in_seconds: number
  user: User
}

export interface DashboardResponse {
  role: UserRole | string
  generated_for_day: string
  data: Record<string, unknown>
}

export interface TimetableEntry {
  id: number
  term_id: number
  entry_kind: 'course' | 'special_event'
  course_code: string | null
  course_name: string | null
  semester: string | null
  section: string | null
  faculty: string | null
  room: string | null
  day: DayName
  start_time: string
  end_time: string
  class_type: ClassType
  raw_text: string | null
  source: 'manual' | 'csv' | 'xlsx' | 'docx' | 'pdf' | 'image' | 'generated'
}

export type DayName = 'Monday' | 'Tuesday' | 'Wednesday' | 'Thursday' | 'Friday' | 'Saturday' | 'Sunday'
export type ClassType = 'lecture' | 'lab' | 'tutorial' | 'online' | 'hybrid' | 'other'

export interface FacultyFreeSlot {
  day: DayName
  start_time: string
  end_time: string
  duration_minutes: number
}

export interface FacultyFreeSlotsResponse {
  term_id: number
  opens_at: string
  closes_at: string
  minimum_minutes: number
  slots: FacultyFreeSlot[]
  note: string
}

export interface Enrollment {
  id: number
  term_id: number
  user_id: number
  course_code: string
  section: string
  semester: string
  created_at: string
}

export interface EnrollmentTimetableClass {
  id: number
  course_code: string | null
  course_name: string | null
  section: string | null
  semester: string | null
  faculty: string | null
  room: string | null
  day: DayName
  start_time: string
  end_time: string
}

export interface EnrollmentConflictValidation {
  course_code: string
  section: string
  semester: string
  mapped_timetable_entry_ids: number[]
  has_conflicts: boolean
  conflicts: Array<{
    proposed_class: EnrollmentTimetableClass
    conflicts_with: EnrollmentTimetableClass
    day: DayName
    overlap_start: string
    overlap_end: string
  }>
  alternate_sections: Array<{
    section: string
    timetable_entry_ids: number[]
    conflict_free: boolean
    validation_status: 'timetable_only_unverified'
    limitations: string[]
  }>
  limitations: string[]
}

export interface EnrollmentCreateResult extends Enrollment {
  conflict_validation: EnrollmentConflictValidation
}

export type ClashReportStatus = 'submitted' | 'under_review' | 'resolved' | 'rejected' | 'duplicate'
export type ClashReportResolutionReason = 'timetable_changed' | 'enrollment_corrected' | 'course_dropped' | 'other_verified_correction'

export interface ClashReportItem {
  id: number
  timetable_entry_id: number | null
  course_code: string
  section: string | null
  semester: string | null
  day: string | null
  start_time: string | null
  end_time: string | null
}

export interface ClashReportEvent {
  id: number
  actor_user_id: number | null
  action: string
  from_status: string | null
  to_status: string | null
  note: string | null
  created_at: string
}

export interface ClashReportSummary {
  id: number
  term_id: number
  student_user_id: number
  student_registration_number: string
  student_name: string
  student_email: string | null
  student_department: string
  student_program: string
  student_batch: string
  student_semester: number
  student_section: string
  conflict_fingerprint: string
  status: ClashReportStatus
  notes: string | null
  evidence_reference: string | null
  duplicate_of_report_id: number | null
  resolution_note: string | null
  resolution_reason: ClashReportResolutionReason | null
  created_at: string
  updated_at: string
  items: ClashReportItem[]
}

export interface ClashReportDetail extends ClashReportSummary {
  events: ClashReportEvent[]
}

export interface ClashReportListResponse {
  reports: ClashReportSummary[]
  total: number
  offset: number
  limit: number
}

export interface ClashReportClusterClass {
  timetable_entry_id: number | null
  course_code: string
  section: string | null
  semester: string | null
  day: string | null
  start_time: string | null
  end_time: string | null
}

export interface ClashReportCluster {
  term_id: number
  conflict_fingerprint: string
  report_ids: number[]
  open_report_ids: number[]
  timetable_entry_ids: number[]
  reported_classes: ClashReportClusterClass[]
  report_count: number
  open_report_count: number
  reporting_student_count: number
  verified_affected_student_count: number
  enrollment_coverage: 'complete' | 'partial' | 'none'
  current_timetable_overlap: boolean
  status_counts: Record<ClashReportStatus, number>
  first_reported_at: string
  latest_reported_at: string
}

export interface ClashReportClusterListResponse {
  clusters: ClashReportCluster[]
  total: number
  offset: number
  limit: number
}


export type CandidateSafetyStatus = 'SAFE' | 'CONDITIONALLY_SAFE' | 'INSUFFICIENT_DATA' | 'REJECTED'

export interface CandidateTimeSlot {
  day: string
  start_time: string
  end_time: string
}

export interface CandidateCheck {
  name: string
  status: 'PASS' | 'WARN' | 'FAIL'
  detail: string
}

export interface CandidateScoreComponent {
  signal: string
  value: number
  explanation: string
}

export interface ResolutionCandidateImpact {
  affected_students: number
  confirmed_conflicts_before: number
  confirmed_conflicts_after: number
  confirmed_conflicts_removed: number
  new_confirmed_conflicts: number
  student_risks_before: number
  student_risks_after: number
  structural_clashes_before: number
  structural_clashes_after: number
  conflict_groups_before: number
  conflict_groups_after: number
  weighted_risk_before: number
  weighted_risk_after: number
  timetable_entries_changed: number
}

export interface ResolutionCandidate {
  candidate_id: string
  status: Exclude<CandidateSafetyStatus, 'REJECTED'>
  actionable_without_confirmation: boolean
  entry_id: number
  course_code: string | null
  course_name: string | null
  section: string | null
  move_from: CandidateTimeSlot
  move_to: CandidateTimeSlot
  duration_minutes: number
  rank_score: number
  score_components: CandidateScoreComponent[]
  ranker: { ranker_id: string; ranker_version: string }
  features: {
    feature_schema_version: '1.0'
    hard_constraints_passed: true
    safety_status: Exclude<CandidateSafetyStatus, 'REJECTED'>
    duration_minutes: number
    affected_students: number
    confirmed_conflicts_removed: number
    inferred_conflicts_removed: number
    structural_clashes_removed: number
    conflict_groups_removed: number
    weighted_risk_reduction: number
    day_distance: number
    time_shift_minutes: number
    late_slot: boolean
    missing_metadata_count: number
  }
  checks: CandidateCheck[]
  missing_data: string[]
  rejection_reasons: string[]
  impact: ResolutionCandidateImpact
}

export interface RejectedResolutionCandidate {
  candidate_id: string
  entry_id: number
  move_to: CandidateTimeSlot
  status: 'REJECTED'
  rejection_reasons: string[]
  checks: CandidateCheck[]
}

export interface ClashReportResolutionCandidatesResponse {
  report_id: number
  report_status: ClashReportStatus
  report_entry_ids: number[]
  target_entry_ids: number[]
  policy: {
    operating_days: string[]
    opens_at: string
    closes_at: string
    slot_interval_minutes: number
    blocked_periods: Array<CandidateTimeSlot & { reason: string }>
  }
  summary: {
    generated: number
    safe: number
    conditionally_safe: number
    insufficient_data: number
    rejected: number
  }
  candidates: ResolutionCandidate[]
  rejected_candidates: RejectedResolutionCandidate[]
  important_note: string
}

export interface ClashReportResolutionApplyResponse {
  success: true
  message: string
  report_id: number
  report_status: 'resolved'
  change_id: number
  candidate_id: string
  safety_status: 'SAFE' | 'CONDITIONALLY_SAFE'
  conditional_confirmation_recorded: boolean
  resolved_report_ids: number[]
  resolved_report_count: number
  applied_candidate: ResolutionCandidate
  report: ClashReportDetail
}

export interface DataQualityIssue {
  issue_code: string
  severity: 'critical' | 'error' | 'warning' | 'info'
  scope: 'global' | 'term'
  entity_type: string
  entity_id: string | null
  message: string
  suggested_correction: string
  related_entity_ids: number[]
}

export interface DataQualityReport {
  term_id: number
  term_code: string
  generated_at: string
  summary: { total: number; critical: number; error: number; warning: number; info: number }
  issues: DataQualityIssue[]
  important_note: string
}

export interface OptionalRateMetric {
  value: number | null
  numerator: number | null
  denominator: number | null
  available: boolean
  reason: string | null
}

export interface ResolverAnalytics {
  term_id: number
  term_code: string
  generated_at: string
  current_confirmed_conflicts: number
  current_inferred_conflicts: number
  current_structural_clashes: number
  current_verified_students: number
  current_enrollment_records: number
  current_affected_student_instances: number
  report_status_counts: Record<ClashReportStatus, number>
  report_total: number
  report_cluster_count: number
  grouped_duplicate_reports: number
  average_first_resolution_hours: number | null
  resolution_applications: number
  resolution_undos: number
  resolution_redos: number
  confirmed_conflicts_removed_by_applications: number
  structural_clashes_removed_by_applications: number
  shared_resolved_reports: number
  shared_resolution_percentage: number | null
  recommendation_acceptance_rate: OptionalRateMetric
  undo_rate: OptionalRateMetric
  redo_rate: OptionalRateMetric
  important_note: string
}

export interface FacultyAssignment {
  id: number
  term_id: number
  faculty_user_id: number
  faculty_name: string
  faculty_email: string
  course_code: string
  section: string
  semester: string
  created_by_user_id: number | null
  created_at: string
}

export interface FacultyDirectoryEntry {
  id: number
  full_name: string
  email: string
}

export interface FacultyDirectoryResponse {
  faculty: FacultyDirectoryEntry[]
  total: number
  offset: number
  limit: number
}

export type FacultyDesignation = 'lecturer' | 'assistant_professor'
export type OfferingClassType = 'lecture' | 'lab'
export type FacultyAvailabilityDay =
  | 'Monday'
  | 'Tuesday'
  | 'Wednesday'
  | 'Thursday'
  | 'Friday'

export interface CourseOffering {
  id: number
  term_id: number
  course_code: string
  course_name: string
  semester: number
  section: string
  class_type: OfferingClassType
  duration_minutes: number
  room: string | null
  created_by_user_id: number | null
  created_at: string
  updated_at: string
}

export interface FacultyWorkload {
  faculty_user_id: number
  faculty_name: string
  faculty_email: string
  designation: FacultyDesignation | null
  profile_configured: boolean
  term_id: number
  distinct_subjects_assigned: number
  maximum_subjects: number | null
  remaining_capacity: number | null
  subject_codes: string[]
}

export interface FacultyAvailability {
  id: number
  term_id: number
  faculty_user_id: number
  day: FacultyAvailabilityDay
  start_time: string
  end_time: string
  created_at: string
  updated_at: string
}

export interface TimetableGenerationProposal {
  offering_id: number
  faculty_user_id: number
  faculty_name: string
  course_code: string
  course_name: string
  semester: number
  section: string
  class_type: OfferingClassType
  room: string
  day: string
  start_time: string
  end_time: string
  duration_minutes: number
}

export interface TimetableGenerationPreview {
  term_id: number
  status: 'READY' | 'BLOCKED'
  preview_id: string
  complete: boolean
  existing_satisfied_entry_ids: number[]
  existing_satisfied_count: number
  proposed_count: number
  readiness_errors: string[]
  unscheduled: string[]
  proposals: TimetableGenerationProposal[]
  policy_note: string
}

export interface TimetableGenerationApplyResponse {
  success: true
  term_id: number
  preview_id: string
  created_count: number
  existing_satisfied_count: number
  entries: TimetableEntry[]
  message: string
}

export interface TimetableTimeChangeResponse {
  entry: TimetableEntry
  change_id: number
  safety: {
    clashes_before: number
    clashes_after: number
    student_risk_cost_before: number
    student_risk_cost_after: number
  }
}

export type NotificationType =
  | 'class_reminder'
  | 'daily_summary'
  | 'schedule_change'
  | 'room_change'
  | 'time_change'
  | 'cancellation'
  | 'clash_report_status'

export interface NotificationItem {
  id: number
  term_id: number
  user_id: number
  type: NotificationType
  title: string
  message: string
  payload: Record<string, unknown>
  read_at: string | null
  created_at: string
}

export interface NotificationListResponse {
  notifications: NotificationItem[]
  total: number
  unread_count: number
  offset: number
  limit: number
}

export interface NotificationPreference {
  user_id: number
  class_reminder_minutes: 5 | 10 | 15 | 30 | null
  daily_summary_enabled: boolean
  daily_summary_time: string
  schedule_change_enabled: boolean
  clash_report_updates_enabled: boolean
  updated_at: string | null
}

export interface AdminUserListResponse {
  users: User[]
  total: number
  offset: number
  limit: number
}

export interface NotificationJobResponse {
  reminders_created: number
  summaries_created: number
  processed_users: number
  timezone: string
}

export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue }
