import { apiRequest, queryString } from './client'
import type { NotificationItem, NotificationJobResponse, NotificationListResponse, NotificationPreference, NotificationType } from '../types/api'

export const notificationsApi = {
  list: (params: { unreadOnly?: boolean; type?: NotificationType | ''; offset?: number; limit?: number } = {}) =>
    apiRequest<NotificationListResponse>(`/notifications${queryString({ unread_only: params.unreadOnly, type: params.type, offset: params.offset ?? 0, limit: params.limit ?? 50 })}`),
  markRead: (id: number) => apiRequest<NotificationItem>(`/notifications/${id}/read`, { method: 'PATCH' }),
  markAllRead: () => apiRequest<unknown>('/notifications/read-all', { method: 'POST' }),
  preferences: () => apiRequest<NotificationPreference>('/notification-preferences'),
  updatePreferences: (payload: Omit<NotificationPreference, 'user_id' | 'updated_at'>) =>
    apiRequest<NotificationPreference>('/notification-preferences', { method: 'PUT', body: payload }),
  processJobs: () => apiRequest<NotificationJobResponse>('/notification-jobs/process', { method: 'POST' }),
}
