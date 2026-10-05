// @vitest-environment happy-dom
import { act, cleanup, render } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals() })
it('polls health every 30 seconds only while visible and cleans up on unmount', async () => {
  vi.useFakeTimers()
  const visible = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
  const fetch = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ status: 'healthy' })))
  vi.stubGlobal('fetch', fetch)
  const view = render(<App />)
  await act(async () => { await vi.advanceTimersByTimeAsync(30_000) })
  expect(fetch).not.toHaveBeenCalled()
  visible.mockReturnValue('visible')
  await act(async () => { await vi.advanceTimersByTimeAsync(30_000) })
  expect(fetch).toHaveBeenCalledTimes(1)
  view.unmount()
  await act(async () => { await vi.advanceTimersByTimeAsync(60_000) })
  expect(fetch).toHaveBeenCalledTimes(1)
})
