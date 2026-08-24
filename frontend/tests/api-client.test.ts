import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiRequest, clearStoredToken, storeToken } from '../src/api/client'

afterEach(() => {
  vi.unstubAllGlobals()
  clearStoredToken()
})

describe('API client', () => {
  it('attaches the bearer token', async () => {
    storeToken('secret-token')
    const fetchMock = vi.fn(async (_url: string, options?: RequestInit) => {
      const headers = new Headers(options?.headers)
      expect(headers.get('Authorization')).toBe('Bearer secret-token')
      return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'content-type': 'application/json' } })
    })
    vi.stubGlobal('fetch', fetchMock)
    await expect(apiRequest<{ ok: boolean }>('/auth/me')).resolves.toEqual({ ok: true })
  })

  it('dispatches unauthorized event on a 401', async () => {
    const handler = vi.fn()
    window.addEventListener('unitime:unauthorized', handler)
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ success: false, error: 'Authentication credentials are invalid or missing.', status_code: 401, request_id: 'req-1' }), { status: 401, headers: { 'content-type': 'application/json' } })))
    await expect(apiRequest('/auth/me')).rejects.toBeInstanceOf(ApiError)
    expect(handler).toHaveBeenCalledTimes(1)
    window.removeEventListener('unitime:unauthorized', handler)
  })

  it('does not dispatch unauthorized for an authenticated 403', async () => {
    const handler = vi.fn()
    window.addEventListener('unitime:unauthorized', handler)
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ success: false, error: 'Forbidden.', status_code: 403 }), { status: 403, headers: { 'content-type': 'application/json' } })))
    await expect(apiRequest('/admin/users')).rejects.toMatchObject({ status: 403 })
    expect(handler).not.toHaveBeenCalled()
    window.removeEventListener('unitime:unauthorized', handler)
  })

  it('uses a nested backend detail message and preserves request metadata', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ success: false, error: 'Request failed.', status_code: 409, request_id: 'req-detail', detail: { message: 'The requested room is occupied.', room: 'CS-301' } }), { status: 409, headers: { 'content-type': 'application/json' } })))
    await expect(apiRequest('/timetable/1/room')).rejects.toMatchObject({
      message: 'The requested room is occupied.',
      status: 409,
      requestId: 'req-detail',
      detail: { room: 'CS-301' },
    })
  })

  it('normalizes transport failures without treating them as authentication failures', async () => {
    const handler = vi.fn()
    window.addEventListener('unitime:unauthorized', handler)
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('network down') }))
    await expect(apiRequest('/auth/me')).rejects.toMatchObject({ status: 0 })
    expect(handler).not.toHaveBeenCalled()
    window.removeEventListener('unitime:unauthorized', handler)
  })
})
