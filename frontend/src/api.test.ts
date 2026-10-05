import { afterEach, expect, it, vi } from 'vitest'
import { request } from './api'

afterEach(() => vi.unstubAllGlobals())
it('hides internal server errors and preserves validation messages', async () => {
  const fetch = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'database secret' }), { status: 500 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ detail: [{ loc: ['body', 'name'], msg: 'Required' }] }), { status: 422 }))
  vi.stubGlobal('fetch', fetch)
  await expect(request('/monitors')).rejects.toThrow('The service is temporarily unavailable.')
  await expect(request('/monitors')).rejects.toThrow('name: Required')
})
