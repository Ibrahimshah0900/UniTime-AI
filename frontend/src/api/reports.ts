import { apiRequest, queryString } from './client'
import type { ClashReportClusterListResponse, ClashReportDetail, ClashReportListResponse, ClashReportResolutionApplyResponse, ClashReportResolutionCandidatesResponse, ClashReportResolutionReason, ClashReportStatus } from '../types/api'

export const reportsApi = {
  queue: (status?: ClashReportStatus | '', offset = 0, limit = 50) =>
    apiRequest<ClashReportListResponse>(`/clash-reports${queryString({ status, offset, limit })}`),
  clusters: (openOnly = true, offset = 0, limit = 50) =>
    apiRequest<ClashReportClusterListResponse>(`/clash-reports/clusters${queryString({ open_only: openOnly, offset, limit })}`),
  detail: (id: number) => apiRequest<ClashReportDetail>(`/clash-reports/${id}`),
  review: (id: number, payload: { status: ClashReportStatus; resolution_note?: string | null; resolution_reason?: ClashReportResolutionReason | null; duplicate_of_report_id?: number | null }) =>
    apiRequest<ClashReportDetail>(`/clash-reports/${id}`, { method: 'PATCH', body: payload }),
  candidates: (id: number, targetEntryId?: number, limit = 20, includeRejectedLimit = 10) =>
    apiRequest<ClashReportResolutionCandidatesResponse>(`/clash-reports/${id}/resolution-candidates${queryString({ target_entry_id: targetEntryId, limit, include_rejected_limit: includeRejectedLimit })}`),
  applyCandidate: (id: number, candidateId: string, payload: { target_entry_id: number; resolution_note: string; confirm_conditional: boolean }) =>
    apiRequest<ClashReportResolutionApplyResponse>(`/clash-reports/${id}/resolution-candidates/${candidateId}/apply`, { method: 'POST', body: payload }),
}
