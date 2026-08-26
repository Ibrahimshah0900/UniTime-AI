import { apiRequest } from './client'
import type { AcademicTerm, AcademicTermListResponse } from '../types/api'

export interface AcademicTermCreatePayload {
  code: string
  name: string
  starts_on?: string | null
  ends_on?: string | null
}

export const termsApi = {
  list: () => apiRequest<AcademicTermListResponse>('/academic-terms'),
  current: () => apiRequest<AcademicTerm>('/academic-terms/current'),
  create: (payload: AcademicTermCreatePayload) => apiRequest<AcademicTerm>('/academic-terms', { method: 'POST', body: payload }),
  activate: (id: number) => apiRequest<AcademicTerm>(`/academic-terms/${id}/activate`, { method: 'POST' }),
  archive: (id: number) => apiRequest<AcademicTerm>(`/academic-terms/${id}/archive`, { method: 'POST' }),
}
