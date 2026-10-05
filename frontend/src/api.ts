export type User = { id: string; email: string; full_name: string }
export type MonitorInput = {
  name: string; url: string; method: 'GET'; interval_seconds: number
  timeout_seconds: number; is_active: boolean
}
export type MonitorCheck = {
  status: 'UP' | 'DOWN'; http_status_code: number | null; response_time_ms: number | null
  error_type: string | null; error_message: string | null; checked_at: string
}
export type Monitor = MonitorInput & {
  id: string; user_id: string; created_at: string; updated_at: string; latest_check: MonitorCheck | null
}

export type DashboardSummary = {
  total_monitors: number
  active_monitors: number
  paused_monitors: number
  up_monitors: number
  open_incidents: number
  down_monitors: number
  pending_monitors: number
  checks_last_24h: number
  average_response_time_ms_24h: number | null
}

export type MonitorStats = {
  monitor_id: string
  window_hours: number
  total_checks: number
  successful_checks: number
  failed_checks: number
  uptime_percentage: number | null
  average_response_time_ms: number | null
  minimum_response_time_ms: number | null
  maximum_response_time_ms: number | null
}

export type MonitorCheckHistory = {
  items: MonitorCheck[]
  total: number
  limit: number
  offset: number
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) { super(message); this.status = status }
}

export async function request<T>(path: string, token?: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController()
  const abort = () => controller.abort()
  signal?.addEventListener('abort', abort, { once: true })
  if (signal?.aborted) controller.abort()
  const timeout = setTimeout(() => controller.abort(), 15_000)
  try {
    const response = await fetch(`/api${path}`, {
      method, signal: controller.signal,
      headers: { ...(body ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    })
    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      const detail = data.detail
      const message = typeof detail === 'string' ? detail : Array.isArray(detail)
        ? detail.map((item: { loc: string[]; msg: string }) => `${item.loc.slice(1).join('.')}: ${item.msg}`).join('; ')
        : `Request failed (${response.status})`
      throw new ApiError(message, response.status)
    }
    return response.status === 204 ? undefined as T : await response.json() as T
  } finally { clearTimeout(timeout); signal?.removeEventListener('abort', abort) }
}

export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Unable to reach the API. Please try again.'
}

export const intervals = [[30, "30 seconds"], [60, "1 minute"], [300, "5 minutes"], [600, "10 minutes"]] as const

export type IncidentStatus = 'OPEN' | 'RESOLVED'
export type Incident = {
  id: string; monitor_id: string; status: IncidentStatus
  started_at: string; opened_at: string; resolved_at: string | null; created_at: string
}
export type Page<T> = { items: T[]; total: number; limit: number; offset: number }
export type IncidentList = Page<Incident>
