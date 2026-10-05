// @vitest-environment happy-dom
import { afterEach, expect, test, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { Incidents } from './Incidents'
import { DashboardSummary } from './DashboardSummary'
import { MonitorDetails } from './MonitorDetails'
import { ApiError, request, type Monitor, type Incident } from './api'
vi.mock('./api', async importOriginal => ({ ...await importOriginal<typeof import('./api')>(), request: vi.fn() }))
vi.mock('./ResponseTimeChart', () => ({ ResponseTimeChart: () => null }))
const api = vi.mocked(request)
const monitor = { id: 'monitor-1', name: 'API', url: 'https://example.com', is_active: true, latest_check: { status: 'DOWN' } } as Monitor
const incident: Incident = { id: 'incident-1', monitor_id: monitor.id, status: 'OPEN', started_at: '2026-10-05T01:00:00Z', opened_at: '2026-10-05T01:02:00Z', resolved_at: null, created_at: '2026-10-05T01:02:00Z' }
afterEach(() => { cleanup(); vi.restoreAllMocks(); api.mockReset(); vi.useRealTimers() })
function setup(onExpired = vi.fn()) { return render(<Incidents token="test-only" monitors={[monitor]} onBack={vi.fn()} onExpired={onExpired} />) }
test('paginates real API results and resets offset when filter changes', async () => {
  api.mockImplementation(async path => ({ items: [incident], total: 51, limit: 50, offset: path.includes('offset=50') ? 50 : 0 }))
  setup()
  await screen.findByText('API')
  fireEvent.change(screen.getByLabelText('Filter by status'), { target: { value: 'OPEN' } })
  await waitFor(() => expect(api.mock.lastCall?.[0]).toContain('offset=0&status=OPEN'))
  await screen.findByText('API')
  fireEvent.click(screen.getByText('Next'))
  await screen.findByText('Showing 51-51 of 51')
  expect(api.mock.lastCall?.[0]).toContain('offset=50&status=OPEN')
  fireEvent.change(screen.getByLabelText('Filter by status'), { target: { value: 'RESOLVED' } })
  await waitFor(() => expect(api.mock.lastCall?.[0]).toContain('offset=0&status=RESOLVED'))
})
test('shows errors, reloads empty state, handles expired session', async () => {
  api.mockRejectedValueOnce(new ApiError('Unavailable', 503)).mockResolvedValueOnce({ items: [], total: 0, offset: 0, limit: 50 }).mockRejectedValueOnce(new ApiError('Expired', 401))
  const expired = vi.fn(); setup(expired)
  await screen.findByRole('alert')
  fireEvent.click(screen.getByText('Reload'))
  await screen.findByText('No incidents recorded.')
  fireEvent.click(screen.getByText('Reload'))
  await waitFor(() => expect(expired).toHaveBeenCalledOnce())
})
test('pauses hidden polling and aborts on unmount', async () => {
  vi.useFakeTimers()
  const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
  api.mockResolvedValue({ items: [], total: 0, offset: 0, limit: 50 })
  const view = setup()
  await act(() => vi.advanceTimersByTimeAsync(30_000))
  expect(api).not.toHaveBeenCalled()
  visibility.mockReturnValue('visible')
  await act(() => vi.advanceTimersByTimeAsync(30_000))
  expect(api).toHaveBeenCalledOnce()
  const signal = api.mock.lastCall?.[4]
  view.unmount()
  expect(signal?.aborted).toBe(true)
  await act(() => vi.advanceTimersByTimeAsync(60_000))
  expect(api).toHaveBeenCalledOnce()
})
test('dashboard counts incidents independently of DOWN', () => {
  render(<DashboardSummary loading={false} summary={{ total_monitors: 5, active_monitors: 5, paused_monitors: 0, up_monitors: 1, down_monitors: 4, open_incidents: 2, pending_monitors: 0, checks_last_24h: 100, average_response_time_ms_24h: null }} />)
  expect(screen.getByText('Open incidents').parentElement?.textContent).toContain('2')
  expect(screen.getByText('Down').parentElement?.textContent).toContain('4')
})
test('details loads incidents with history and derives fresh operational status', async () => {
  api.mockImplementation(async path => path.includes('/stats') ? {} : path.includes('/checks') ? { items: [{ ...monitor.latest_check, status: 'UP', checked_at: incident.opened_at }], total: 1 } : { items: [incident], total: 1, offset: 0, limit: 50 })
  render(<MonitorDetails token="test-only" monitor={monitor} onBack={vi.fn()} onExpired={vi.fn()} />)
  await screen.findByText('OPEN')
  expect(screen.queryByText('DOWN')).toBeNull()
  expect(screen.getAllByText('UP')).toHaveLength(2)
})
