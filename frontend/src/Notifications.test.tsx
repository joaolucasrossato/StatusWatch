// @vitest-environment happy-dom
import { afterEach, expect, test, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { Notifications } from './Notifications'
import { ApiError, request, type Monitor, type NotificationChannel } from './api'
vi.mock('./api', async importOriginal => ({ ...await importOriginal<typeof import('./api')>(), request: vi.fn() }))
const api = vi.mocked(request)
const monitor = { id: 'monitor-1', name: 'API' } as Monitor
const channel: NotificationChannel = { id: 'channel-1', monitor_id: monitor.id, type: 'WEBHOOK', target: 'https://example.com/…', target_redacted: true, is_active: true, notify_on_open: true, notify_on_resolved: true, created_at: '2026-10-05T01:00:00Z', updated_at: '2026-10-05T01:00:00Z' }
const empty = { items: [], total: 0, offset: 0, limit: 50 }
afterEach(() => { cleanup(); vi.restoreAllMocks(); api.mockReset(); vi.useRealTimers() })
function setup(channels: NotificationChannel[] = [], onExpired = vi.fn()) {
  api.mockImplementation(async (path, _token, method = 'GET') => method !== 'GET' ? channel : path.includes('/notification-channels') ? channels : empty)
  return render(<Notifications token="test-only" monitor={monitor} onBack={vi.fn()} onExpired={onExpired} />)
}

test.each(['EMAIL', 'WEBHOOK'])('creates %s with event preferences and monitor ownership', async type => {
  setup()
  await screen.findByText('No notification channels configured.')
  fireEvent.click(screen.getByText('Add channel'))
  fireEvent.change(screen.getByLabelText('Channel type'), { target: { value: type } })
  fireEvent.change(screen.getByLabelText(type === 'EMAIL' ? 'Email address' : 'Webhook URL'), { target: { value: type === 'EMAIL' ? 'alerts@example.com' : 'https://example.com/hook' } })
  fireEvent.click(screen.getByLabelText('Incident resolved'))
  fireEvent.click(screen.getByText('Save channel'))
  await waitFor(() => expect(api).toHaveBeenCalledWith('/notification-channels', 'test-only', 'POST', expect.objectContaining({ monitor_id: monitor.id, type, notify_on_open: true, notify_on_resolved: false }), expect.any(AbortSignal)))
})

test('keeps redacted target on edit, toggles and confirms deletion', async () => {
  setup([channel])
  await screen.findByText(channel.target)
  fireEvent.click(screen.getByText('Edit'))
  expect((screen.getByLabelText(/Webhook URL/) as HTMLInputElement).value).toBe('')
  fireEvent.click(screen.getByLabelText('Incident opened'))
  fireEvent.click(screen.getByText('Save channel'))
  await waitFor(() => expect(api).toHaveBeenCalledWith('/notification-channels/channel-1', 'test-only', 'PATCH', { is_active: true, notify_on_open: false, notify_on_resolved: true }, expect.any(AbortSignal)))
  await waitFor(() => expect(screen.queryByText('Save channel')).toBeNull())
  fireEvent.click(screen.getByText('Disable'))
  await waitFor(() => expect(api).toHaveBeenCalledWith('/notification-channels/channel-1', 'test-only', 'PATCH', { is_active: false }, expect.any(AbortSignal)))
  await waitFor(() => expect((screen.getByText('Delete') as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(screen.getByText('Delete'))
  expect(api.mock.calls.some(call => call[2] === 'DELETE')).toBe(false)
  fireEvent.click(screen.getByText('Confirm delete'))
  await waitFor(() => expect(api).toHaveBeenCalledWith('/notification-channels/channel-1', 'test-only', 'DELETE', undefined, expect.any(AbortSignal)))
})

test('filters and paginates delivery history', async () => {
  const data = { id: 'delivery-1', channel_id: channel.id, event_type: 'INCIDENT_OPENED', status: 'FAILED', attempt_count: 3, last_error: 'smtp_not_configured', created_at: channel.created_at, sent_at: null }
  setup([channel])
  await screen.findByText('No deliveries recorded.')
  api.mockImplementation(async path => path.includes('/notification-channels') ? [channel] : { items: [data], total: 51, limit: 50, offset: path.includes('offset=50') ? 50 : 0 })
  fireEvent.change(screen.getByLabelText('Delivery status'), { target: { value: 'FAILED' } })
  await screen.findByText('smtp_not_configured')
  fireEvent.click(screen.getByText('Next'))
  await screen.findByText('Showing 51-51 of 51')
  expect(api.mock.calls.some(call => call[0].includes('offset=50&status=FAILED'))).toBe(true)
  fireEvent.change(screen.getByLabelText('Event'), { target: { value: 'INCIDENT_RESOLVED' } })
  await waitFor(() => expect(api.mock.calls.some(call => call[0].includes('offset=0&status=FAILED&event_type=INCIDENT_RESOLVED'))).toBe(true))
})

test('shows mutation error and expires session without exposing input', async () => {
  const expired = vi.fn(); setup([channel], expired)
  await screen.findByText(channel.target)
  api.mockRejectedValue(new ApiError('Invalid public destination', 422))
  fireEvent.click(screen.getByText('Edit'))
  fireEvent.change(screen.getByLabelText(/Webhook URL/), { target: { value: 'https://localhost' } })
  fireEvent.click(screen.getByText('Save channel'))
  await screen.findByText('Invalid public destination')
  expect(screen.getByText('Save channel')).toBeTruthy()
  api.mockRejectedValue(new ApiError('Expired', 401))
  fireEvent.click(screen.getByText('Save channel'))
  await waitFor(() => expect(expired).toHaveBeenCalledOnce())
})

test('does not poll while hidden or after unmount', async () => {
  vi.useFakeTimers()
  const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
  const view = setup()
  await act(() => vi.advanceTimersByTimeAsync(30_000))
  expect(api).not.toHaveBeenCalled()
  visibility.mockReturnValue('visible')
  await act(() => vi.advanceTimersByTimeAsync(30_000))
  expect(api).toHaveBeenCalledTimes(2)
  view.unmount()
  await act(() => vi.advanceTimersByTimeAsync(60_000))
  expect(api).toHaveBeenCalledTimes(2)
})
