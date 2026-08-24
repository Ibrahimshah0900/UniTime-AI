import { apiRequest } from './client'
import type { DashboardResponse } from '../types/api'

export const dashboardApi = {
  get: () => apiRequest<DashboardResponse>('/dashboard'),
}
