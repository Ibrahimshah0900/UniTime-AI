import { apiRequest, queryString } from './client'
import type { ClashReportDetail, ClashReportListResponse, Enrollment, EnrollmentConflictValidation, EnrollmentCreateResult, TimetableEntry } from '../types/api'

export const studentApi = {
  timetable: () => apiRequest<TimetableEntry[]>('/student/timetable'),
  enrollments: () => apiRequest<Enrollment[]>('/student/enrollments'),
  validateEnrollment: (payload: { course_code: string; section: string; semester: string }) =>
    apiRequest<EnrollmentConflictValidation>('/student/enrollments/validate', { method: 'POST', body: payload }),
  addEnrollment: (payload: { course_code: string; section: string; semester: string }) =>
    apiRequest<EnrollmentCreateResult>('/student/enrollments', { method: 'POST', body: payload }),
  removeEnrollment: (id: number) => apiRequest<void>(`/student/enrollments/${id}`, { method: 'DELETE' }),
  clashReports: (offset = 0, limit = 50) => apiRequest<ClashReportListResponse>(`/student/clash-reports${queryString({ offset, limit })}`),
  clashReport: (id: number) => apiRequest<ClashReportDetail>(`/student/clash-reports/${id}`),
  submitClashReport: (payload: { timetable_entry_ids: number[]; notes?: string | null; evidence_reference?: string | null }) =>
    apiRequest<ClashReportDetail>('/student/clash-reports', { method: 'POST', body: payload }),
}
