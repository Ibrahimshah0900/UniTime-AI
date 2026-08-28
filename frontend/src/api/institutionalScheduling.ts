import { apiRequest, queryString } from './client'
import type {
  CourseOffering,
  FacultyAvailability,
  FacultyAvailabilityDay,
  FacultyDesignation,
  FacultyWorkload,
  OfferingClassType,
  TimetableGenerationApplyResponse,
  TimetableGenerationPreview,
} from '../types/api'

export interface CourseOfferingCreatePayload {
  term_id: number
  course_code: string
  course_name: string
  semester: number
  section: string
  class_type: OfferingClassType
  duration_minutes: number
  room: string | null
}

export type CourseOfferingUpdatePayload = Partial<
  Omit<CourseOfferingCreatePayload, 'term_id'>
>

export interface FacultyAvailabilityCreatePayload {
  term_id: number
  day: FacultyAvailabilityDay
  start_time: string
  end_time: string
}

export interface ManagedFacultyAvailabilityCreatePayload
  extends FacultyAvailabilityCreatePayload {
  faculty_user_id: number
}

export const institutionalSchedulingApi = {
  courseOfferings: (termId?: number | null) =>
    apiRequest<CourseOffering[]>(
      `/course-offerings${queryString({ term_id: termId || undefined })}`,
    ),
  createCourseOffering: (payload: CourseOfferingCreatePayload) =>
    apiRequest<CourseOffering>('/course-offerings', {
      method: 'POST',
      body: payload,
    }),
  updateCourseOffering: (
    offeringId: number,
    payload: CourseOfferingUpdatePayload,
  ) =>
    apiRequest<CourseOffering>(`/course-offerings/${offeringId}`, {
      method: 'PATCH',
      body: payload,
    }),
  deleteCourseOffering: (offeringId: number) =>
    apiRequest<void>(`/course-offerings/${offeringId}`, {
      method: 'DELETE',
    }),

  workloads: (termId?: number | null, facultyUserId?: number | null) =>
    apiRequest<FacultyWorkload[]>(
      `/faculty-teaching-profiles${queryString({
        term_id: termId || undefined,
        faculty_user_id: facultyUserId || undefined,
      })}`,
    ),
  setDesignation: (
    facultyUserId: number,
    designation: FacultyDesignation,
    termId?: number | null,
  ) =>
    apiRequest<FacultyWorkload>(
      `/faculty-teaching-profiles/${facultyUserId}${queryString({
        term_id: termId || undefined,
      })}`,
      { method: 'PUT', body: { designation } },
    ),

  managedAvailability: (facultyUserId: number, termId?: number | null) =>
    apiRequest<FacultyAvailability[]>(
      `/faculty-availability${queryString({
        faculty_user_id: facultyUserId,
        term_id: termId || undefined,
      })}`,
    ),
  addManagedAvailability: (
    payload: ManagedFacultyAvailabilityCreatePayload,
  ) =>
    apiRequest<FacultyAvailability>('/faculty-availability', {
      method: 'POST',
      body: payload,
    }),
  deleteManagedAvailability: (windowId: number) =>
    apiRequest<void>(`/faculty-availability/${windowId}`, {
      method: 'DELETE',
    }),

  myAvailability: (termId?: number | null) =>
    apiRequest<FacultyAvailability[]>(
      `/faculty/availability${queryString({
        term_id: termId || undefined,
      })}`,
    ),
  addMyAvailability: (payload: FacultyAvailabilityCreatePayload) =>
    apiRequest<FacultyAvailability>('/faculty/availability', {
      method: 'POST',
      body: payload,
    }),
  deleteMyAvailability: (windowId: number) =>
    apiRequest<void>(`/faculty/availability/${windowId}`, {
      method: 'DELETE',
    }),

  previewGeneration: (termId: number) =>
    apiRequest<TimetableGenerationPreview>('/timetable-generation/preview', {
      method: 'POST',
      body: { term_id: termId },
    }),
  applyGeneration: (termId: number, previewId: string) =>
    apiRequest<TimetableGenerationApplyResponse>(
      '/timetable-generation/apply',
      {
        method: 'POST',
        body: { term_id: termId, preview_id: previewId },
      },
    ),
}
