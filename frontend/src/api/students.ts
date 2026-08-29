import { apiRequest, queryString } from './client'
import type {
  RosterImportResponse,
  StudentAcademicStatus,
  StudentIdentity,
  StudentIdentityListResponse,
  StudentProvisionResponse,
  TemporaryCredentialResponse,
} from '../types/api'

export interface StudentProvisionPayload {
  registration_number: string
  full_name: string
  email?: string | null
  department: string
  program: string
  batch: string
  current_semester: number
  section: string
  academic_status?: StudentAcademicStatus
  is_verified?: boolean
  is_active?: boolean
  temporary_password?: string | null
}

export interface StudentIdentityUpdatePayload {
  registration_number?: string
  full_name?: string
  email?: string | null
  department?: string
  program?: string
  batch?: string
  current_semester?: number
  section?: string
  academic_status?: StudentAcademicStatus
  is_verified?: boolean
  is_active?: boolean
}

export const studentsApi = {
  list: (
    params: {
      search?: string
      isVerified?: boolean | ''
      isActive?: boolean | ''
      offset?: number
      limit?: number
    } = {},
  ) =>
    apiRequest<StudentIdentityListResponse>(
      `/students${queryString({
        search: params.search,
        is_verified: params.isVerified,
        is_active: params.isActive,
        offset: params.offset ?? 0,
        limit: params.limit ?? 50,
      })}`,
    ),
  provision: (payload: StudentProvisionPayload) =>
    apiRequest<StudentProvisionResponse>('/students', {
      method: 'POST',
      body: payload,
    }),
  update: (userId: number, payload: StudentIdentityUpdatePayload) =>
    apiRequest<StudentIdentity>(`/students/${userId}`, {
      method: 'PATCH',
      body: payload,
    }),
  resetTemporaryPassword: (userId: number) =>
    apiRequest<TemporaryCredentialResponse>(
      `/students/${userId}/temporary-password`,
      { method: 'POST' },
    ),
  importRoster: (
    file: File,
    options: { dryRun: boolean; updateExisting: boolean },
  ) => {
    const formData = new FormData()
    formData.append('file', file)
    return apiRequest<RosterImportResponse>(
      `/students/import${queryString({
        dry_run: options.dryRun,
        update_existing: options.updateExisting,
      })}`,
      { method: 'POST', formData },
    )
  },
  completeOnboarding: (preferredName: string | null) =>
    apiRequest<StudentIdentity>('/account/student-profile', {
      method: 'PATCH',
      body: {
        preferred_name: preferredName,
        complete_onboarding: true,
      },
    }),
}
