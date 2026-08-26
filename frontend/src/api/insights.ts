import { apiRequest, queryString } from './client'
import type { DataQualityReport, ResolverAnalytics } from '../types/api'

export const insightsApi = {
  dataQuality: (termId?: number) =>
    apiRequest<DataQualityReport>(`/data-quality${queryString({ term_id: termId })}`),
  resolverAnalytics: (termId?: number) =>
    apiRequest<ResolverAnalytics>(`/resolver-analytics${queryString({ term_id: termId })}`),
}
