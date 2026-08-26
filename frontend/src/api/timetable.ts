import { apiRequest } from './client'
import type { TimetableEntry, ClassType, DayName, TimetableTimeChangeResponse } from '../types/api'

export interface TimetableCreatePayload {
  entry_kind?: 'course' | 'special_event'
  course_code?: string | null
  course_name?: string | null
  semester?: string | null
  section?: string | null
  faculty?: string | null
  room?: string | null
  day: DayName
  start_time: string
  end_time: string
  class_type?: ClassType
  raw_text?: string | null
  source?: 'manual' | 'csv' | 'xlsx' | 'docx' | 'pdf' | 'image'
}

function termQuery(termId?: number | null) {
  return termId ? `?term_id=${termId}` : ''
}

export const timetableApi = {
  list: (termId?: number | null) => apiRequest<TimetableEntry[]>(`/timetable${termQuery(termId)}`),
  get: (id: number) => apiRequest<TimetableEntry>(`/timetable/${id}`),
  create: (payload: TimetableCreatePayload, termId?: number | null) => apiRequest<TimetableEntry>(`/timetable${termQuery(termId)}`, { method: 'POST', body: payload }),
  remove: (id: number) => apiRequest<void>(`/timetable/${id}`, { method: 'DELETE' }),
  changeRoom: (id: number, room: string) => apiRequest<TimetableEntry>(`/timetable/${id}/room`, { method: 'PATCH', body: { room } }),
  changeTime: (id: number, payload: { day: DayName; start_time: string; end_time: string }) => apiRequest<TimetableTimeChangeResponse>(`/timetable/${id}/time`, { method: 'PATCH', body: payload }),
  importFile: (file: File, termId?: number | null) => {
    const formData = new FormData()
    formData.append('file', file)
    return apiRequest<unknown>(`/timetable/import${termQuery(termId)}`, { method: 'POST', formData })
  },
}
