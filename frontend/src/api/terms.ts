import { apiRequest } from './client'
import type { AcademicTerm, AcademicTermListResponse } from '../types/api'

export interface AcademicTermCreatePayload {
  code: string
  name: string
  starts_on?: string | null
  ends_on?: string | null
}

export const academicTermsApi = {
  list: () => apiRequest<AcademicTermListResponse>('/academic-terms'),
  current: () => apiRequest<AcademicTerm>('/academic-terms/current'),
  create: (payload: AcademicTermCreatePayload) =>
    apiRequest<AcademicTerm>('/academic-terms', { method: 'POST', body: payload }),
  activate: (termId: number) =>
    apiRequest<AcademicTerm>(`/academic-terms/${termId}/activate`, { method: 'POST' }),
  archive: (termId: number) =>
    apiRequest<AcademicTerm>(`/academic-terms/${termId}/archive`, { method: 'POST' }),
}
