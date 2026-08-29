import { apiRequest } from './client'
import type { TokenResponse, User } from '../types/api'

export const authApi = {
  login: (identifier: string, password: string) => apiRequest<TokenResponse>('/auth/login', {
    method: 'POST', body: { identifier, password }, token: null,
  }),
  register: (full_name: string, email: string, password: string) => apiRequest<User>('/auth/register', {
    method: 'POST', body: { full_name, email, password }, token: null,
  }),
  me: () => apiRequest<User>('/auth/me'),
  updateProfile: (full_name: string) => apiRequest<User>('/account/profile', {
    method: 'PATCH', body: { full_name },
  }),
  changePassword: (current_password: string, new_password: string) => apiRequest<void>('/account/change-password', {
    method: 'POST', body: { current_password, new_password },
  }),
}
