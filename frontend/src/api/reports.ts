import { apiRequest, queryString } from './client'
import type { ClashReportClusterListResponse, ClashReportDetail, ClashReportListResponse, ClashReportResolutionReason, ClashReportStatus } from '../types/api'

export const reportsApi = {
  queue: (status?: ClashReportStatus | '', offset = 0, limit = 50) =>
    apiRequest<ClashReportListResponse>(`/clash-reports${queryString({ status, offset, limit })}`),
  clusters: (openOnly = true, offset = 0, limit = 50) =>
    apiRequest<ClashReportClusterListResponse>(`/clash-reports/clusters${queryString({ open_only: openOnly, offset, limit })}`),
  detail: (id: number) => apiRequest<ClashReportDetail>(`/clash-reports/${id}`),
  review: (id: number, payload: { status: ClashReportStatus; resolution_note?: string | null; resolution_reason?: ClashReportResolutionReason | null; duplicate_of_report_id?: number | null }) =>
    apiRequest<ClashReportDetail>(`/clash-reports/${id}`, { method: 'PATCH', body: payload }),
}
