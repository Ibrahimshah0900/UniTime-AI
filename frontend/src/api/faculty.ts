import { apiRequest, queryString } from './client'
import type { FacultyAssignment, FacultyDirectoryResponse, FacultyFreeSlotsResponse, TimetableEntry } from '../types/api'

export const facultyApi = {
  assignments: (termId?: number | null) => apiRequest<FacultyAssignment[]>(`/faculty/assignments${queryString({ term_id: termId })}`),
  timetable: (termId?: number | null) => apiRequest<TimetableEntry[]>(`/faculty/timetable${queryString({ term_id: termId })}`),
  freeSlots: (termId?: number | null, minimumMinutes = 30) =>
    apiRequest<FacultyFreeSlotsResponse>(`/faculty/free-slots${queryString({ term_id: termId, minimum_minutes: minimumMinutes })}`),
  directory: (search = '', offset = 0, limit = 50) => apiRequest<FacultyDirectoryResponse>(`/faculty-directory${queryString({ search, offset, limit })}`),
  managedAssignments: (facultyUserId?: number, termId?: number | null) => apiRequest<FacultyAssignment[]>(`/faculty-assignments${queryString({ faculty_user_id: facultyUserId, term_id: termId })}`),
  addAssignment: (payload: { faculty_user_id: number; term_id?: number; course_code: string; section: string; semester: string }) =>
    apiRequest<FacultyAssignment>('/faculty-assignments', { method: 'POST', body: payload }),
  removeAssignment: (id: number) => apiRequest<void>(`/faculty-assignments/${id}`, { method: 'DELETE' }),
}
