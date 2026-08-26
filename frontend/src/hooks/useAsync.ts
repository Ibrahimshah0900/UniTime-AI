import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'

export function useAsync<T>(loader: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const requestGeneration = useRef(0)

  const load = useCallback(async () => {
    const generation = ++requestGeneration.current
    setLoading(true)
    setError(null)
    try {
      const value = await loader()
      if (requestGeneration.current === generation) setData(value)
      return value
    } catch (err) {
      if (requestGeneration.current === generation) {
        setError(
          err instanceof ApiError
            ? err.message
            : err instanceof Error
              ? err.message
              : 'Request failed',
        )
      }
      return null
    } finally {
      if (requestGeneration.current === generation) setLoading(false)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    void load()
    return () => {
      requestGeneration.current += 1
    }
  }, [load])

  return { data, setData, loading, error, reload: load }
}
