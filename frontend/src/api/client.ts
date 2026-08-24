const TOKEN_KEY = 'unitime_access_token'

export interface ApiValidationDetail {
  location?: Array<string | number>
  message?: string
  type?: string
}

export class ApiError extends Error {
  status: number
  requestId: string | null
  details: ApiValidationDetail[]
  detail: unknown

  constructor(message: string, status: number, requestId: string | null = null, details: ApiValidationDetail[] = [], detail: unknown = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.requestId = requestId
    this.details = details
    this.detail = detail
  }
}

export function getApiBaseUrl() {
  return (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
}

export function getStoredToken() {
  return sessionStorage.getItem(TOKEN_KEY)
}

export function storeToken(token: string) {
  sessionStorage.setItem(TOKEN_KEY, token)
}

export function clearStoredToken() {
  sessionStorage.removeItem(TOKEN_KEY)
}

export interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown
  formData?: FormData
  token?: string | null
}

function validationDetails(value: unknown): ApiValidationDetail[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item) => {
    if (!item || typeof item !== 'object') return []
    const record = item as Record<string, unknown>
    const location = Array.isArray(record.location)
      ? record.location
      : Array.isArray(record.loc)
        ? record.loc
        : undefined
    const message = typeof record.message === 'string'
      ? record.message
      : typeof record.msg === 'string'
        ? record.msg
        : undefined
    const type = typeof record.type === 'string' ? record.type : undefined
    return [{ location: location as Array<string | number> | undefined, message, type }]
  })
}

function detailMessage(detail: unknown): string | null {
  if (typeof detail === 'string' && detail.trim()) return detail
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const message = (detail as Record<string, unknown>).message
    if (typeof message === 'string' && message.trim()) return message
  }
  return null
}

function normalizeError(payload: unknown, status: number, fallbackRequestId: string | null = null): ApiError {
  if (payload && typeof payload === 'object') {
    const record = payload as Record<string, unknown>
    const details = validationDetails(record.details)
    const nestedMessage = detailMessage(record.detail)
    const baseMessage = typeof record.error === 'string' && record.error.trim()
      ? record.error
      : nestedMessage || `Request failed with status ${status}`
    const firstValidationMessage = details.find((item) => item.message)?.message
    const message = nestedMessage && baseMessage === 'Request failed.'
      ? nestedMessage
      : firstValidationMessage && baseMessage === 'Request validation failed.'
        ? `${baseMessage} ${firstValidationMessage}`
        : baseMessage
    const requestId = typeof record.request_id === 'string' ? record.request_id : fallbackRequestId
    return new ApiError(message, status, requestId, details, record.detail)
  }
  return new ApiError(`Request failed with status ${status}`, status, fallbackRequestId)
}

function requestTimeoutMs() {
  const configured = Number(import.meta.env.VITE_API_TIMEOUT_MS || 15_000)
  return Number.isFinite(configured) && configured >= 1_000 ? configured : 15_000
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const token = options.token === undefined ? getStoredToken() : options.token
  const headers = new Headers(options.headers)
  let body: BodyInit | undefined

  if (options.formData) {
    body = options.formData
  } else if (options.body !== undefined) {
    headers.set('Content-Type', 'application/json')
    body = JSON.stringify(options.body)
  }

  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (!headers.has('Accept')) headers.set('Accept', 'application/json')

  const timeoutSignal = AbortSignal.timeout(requestTimeoutMs())
  const signal = options.signal ? AbortSignal.any([options.signal, timeoutSignal]) : timeoutSignal
  let response: Response
  try {
    response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...options,
      headers,
      body,
      signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'TimeoutError') {
      throw new ApiError('The request timed out. Check the backend connection and try again.', 0)
    }
    if (error instanceof DOMException && error.name === 'AbortError' && options.signal?.aborted) {
      throw error
    }
    throw new ApiError('Unable to reach the UniTime-AI backend. Check the connection and try again.', 0)
  }

  if (response.status === 204) return undefined as T

  const contentType = response.headers.get('content-type') || ''
  const raw = await response.text()
  let payload: unknown = raw
  if (raw && contentType.includes('application/json')) {
    try { payload = JSON.parse(raw) } catch { payload = raw }
  }

  if (!response.ok) {
    const error = normalizeError(payload, response.status, response.headers.get('X-Request-ID'))
    if (response.status === 401) window.dispatchEvent(new CustomEvent('unitime:unauthorized'))
    throw error
  }

  return payload as T
}

export function queryString(params: Record<string, string | number | boolean | null | undefined>) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  })
  const serialized = search.toString()
  return serialized ? `?${serialized}` : ''
}
