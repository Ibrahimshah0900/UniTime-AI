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
  source: 'manual' | 'csv' | 'xlsx' | 'docx' | 'pdf' | 'image'
}

export type DayName = 'Monday' | 'Tuesday' | 'Wednesday' | 'Thursday' | 'Friday' | 'Saturday' | 'Sunday'
export type ClassType = 'lecture' | 'lab' | 'tutorial' | 'online' | 'hybrid' | 'other'

export interface Enrollment {
  id: number
  term_id: number
  user_id: number
  course_code: string
  section: string
  semester: string
  created_at: string
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
