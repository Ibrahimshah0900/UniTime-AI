import { act, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useAsync } from '../src/hooks/useAsync'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function Probe({
  termId,
  loaders,
}: {
  termId: number
  loaders: Record<number, Promise<string>>
}) {
  const state = useAsync(() => loaders[termId], [termId])
  return (
    <div>
      <span data-testid="data">{state.data ?? 'none'}</span>
      <span data-testid="loading">{String(state.loading)}</span>
      <span data-testid="error">{state.error ?? 'none'}</span>
    </div>
  )
}

describe('useAsync request ordering', () => {
  it('ignores an older response that finishes after a newer dependency request', async () => {
    const active = deferred<string>()
    const planning = deferred<string>()
    const loaders = { 1: active.promise, 2: planning.promise }

    const view = render(<Probe termId={1} loaders={loaders} />)
    view.rerender(<Probe termId={2} loaders={loaders} />)

    await act(async () => {
      planning.resolve('planning-term-data')
      await planning.promise
    })

    await waitFor(() =>
      expect(screen.getByTestId('data')).toHaveTextContent('planning-term-data'),
    )
    expect(screen.getByTestId('loading')).toHaveTextContent('false')

    await act(async () => {
      active.resolve('stale-active-term-data')
      await active.promise
    })

    expect(screen.getByTestId('data')).toHaveTextContent('planning-term-data')
    expect(screen.getByTestId('error')).toHaveTextContent('none')
    expect(screen.getByTestId('loading')).toHaveTextContent('false')
  })
})
