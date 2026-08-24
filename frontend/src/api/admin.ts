import { apiRequest, queryString } from './client'
import type { AdminUserListResponse, User, UserRole } from '../types/api'

export const adminApi = {
  users: (params: { role?: UserRole | ''; isActive?: boolean | ''; search?: string; offset?: number; limit?: number } = {}) =>
    apiRequest<AdminUserListResponse>(`/admin/users${queryString({ role: params.role, is_active: params.isActive, search: params.search, offset: params.offset ?? 0, limit: params.limit ?? 50 })}`),
  createUser: (payload: { full_name: string; email: string; password: string; role: UserRole }) =>
    apiRequest<User>('/admin/users', { method: 'POST', body: payload }),
  updateUser: (id: number, payload: { full_name?: string | null; role?: UserRole | null; is_active?: boolean | null }) =>
    apiRequest<User>(`/admin/users/${id}`, { method: 'PATCH', body: payload }),
}
