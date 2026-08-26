import { afterEach, describe, expect, it, vi } from 'vitest'
import { reportsApi } from '../src/api/reports'
import { insightsApi } from '../src/api/insights'

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('resolver API clients', () => {
  it('requests report-scoped candidates with ranking limits', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain('/clash-reports/42/resolution-candidates')
      expect(String(input)).toContain('target_entry_id=9')
      expect(String(input)).toContain('limit=12')
      expect(String(input)).toContain('include_rejected_limit=4')
      return jsonResponse({ report_id: 42, candidates: [], rejected_candidates: [], summary: {} })
    })
    vi.stubGlobal('fetch', fetchMock)

    await reportsApi.candidates(42, 9, 12, 4)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('applies a candidate through the transactional report endpoint', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toContain('/clash-reports/42/resolution-candidates/candidate-123/apply')
      expect(init?.method).toBe('POST')
      expect(JSON.parse(String(init?.body))).toEqual({
        target_entry_id: 9,
        resolution_note: 'Verified safe move.',
        confirm_conditional: true,
      })
      return jsonResponse({ success: true })
    })
    vi.stubGlobal('fetch', fetchMock)

    await reportsApi.applyCandidate(42, 'candidate-123', {
      target_entry_id: 9,
      resolution_note: 'Verified safe move.',
      confirm_conditional: true,
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('requests term-scoped quality and analytics diagnostics', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      expect(url.includes('/data-quality') || url.includes('/resolver-analytics')).toBe(true)
      expect(url).toContain('term_id=7')
      return jsonResponse({})
    })
    vi.stubGlobal('fetch', fetchMock)

    await insightsApi.dataQuality(7)
    await insightsApi.resolverAnalytics(7)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
