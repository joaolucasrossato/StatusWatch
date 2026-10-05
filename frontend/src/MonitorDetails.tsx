import { useEffect, useState } from 'react'
import {
  ApiError,
  errorMessage,
  request,
  type Monitor,
  type IncidentList,
  type MonitorCheckHistory,
  type MonitorStats,
} from './api'
import { IncidentTable, Pagination } from './Incidents'
import { Notifications } from './Notifications'
import { ResponseTimeChart } from './ResponseTimeChart'

type Props = {
  monitor: Monitor
  token: string
  onBack: () => void
  onExpired: () => void
}

function formatMilliseconds(value: number | null) {
  return value === null
    ? '—'
    : `${Math.round(value)} ms`
}

function formatPercentage(value: number | null) {
  return value === null
    ? '—'
    : `${value.toFixed(2)}%`
}

export function MonitorDetails({
  monitor,
  token,
  onBack,
  onExpired,
}: Props) {
  const [showNotifications, setShowNotifications] = useState(false)
  const [incidents, setIncidents] = useState<IncidentList | null>(null)
  const [incidentOffset, setIncidentOffset] = useState(0)
  const [stats, setStats] = useState<MonitorStats | null>(null)
  const [history, setHistory] =
    useState<MonitorCheckHistory | null>(null)

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    if (showNotifications) return
    let disposed = false
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>

    async function loadDetails() {
      if (document.visibilityState === 'hidden') {
        if (!disposed) {
          timer = setTimeout(loadDetails, 30_000)
        }

        return
      }

      try {
        const [statsData, historyData, incidentData] = await Promise.all([
          request<MonitorStats>(
            `/monitors/${monitor.id}/stats?window_hours=24`,
            token, 'GET', undefined, controller.signal,
          ),
          request<MonitorCheckHistory>(
            `/monitors/${monitor.id}/checks?limit=50&offset=0`,
            token, 'GET', undefined, controller.signal,
          ),
          request<IncidentList>(
            `/monitors/${monitor.id}/incidents?limit=50&offset=${incidentOffset}`,
            token, 'GET', undefined, controller.signal,
          ),
        ])

        if (!disposed) {
          setIncidents(incidentData)
          if (incidentData.total > 0 && incidentOffset >= incidentData.total) setIncidentOffset(0)
          setStats(statsData)
          setHistory(historyData)
          setError('')
        }
      } catch (failure) {
        if (!disposed) {
          if (
            failure instanceof ApiError
            && [401, 403].includes(failure.status)
          ) {
            onExpired()
          } else {
            setError(errorMessage(failure))
          }
        }
      } finally {
        if (!disposed) {
          setLoading(false)
          timer = setTimeout(loadDetails, 30_000)
        }
      }
    }

    void loadDetails()

    return () => {
      disposed = true
      controller.abort()
      clearTimeout(timer)
    }
  }, [
    monitor.id,
    token,
    onExpired,
    refresh,
    incidentOffset,
    showNotifications,
  ])

  if (showNotifications) return <Notifications monitor={monitor} token={token} onExpired={onExpired} onBack={() => setShowNotifications(false)} />

  const operationalStatus =
    history?.items[0]?.status ?? monitor.latest_check?.status ?? 'Pending'

  return (
    <>
      <div className="details-navigation actions">
        <button
          className="text-button"
          onClick={onBack}
        >
          ← Back to monitors
        </button>
        <button onClick={() => setShowNotifications(true)}>Notifications</button>
      </div>

      <div className="page-heading monitor-detail-heading">
        <div>
          <p className="eyebrow">
            Monitor details
          </p>

          <h1>{monitor.name}</h1>

          <a
            className="detail-url"
            href={monitor.url}
            target="_blank"
            rel="noreferrer"
          >
            {monitor.url}
          </a>
        </div>

        <div className="detail-statuses">
          <span
            className={`badge ${
              monitor.is_active
                ? 'active'
                : 'paused'
            }`}
          >
            {monitor.is_active
              ? 'Active'
              : 'Paused'}
          </span>

          <span
            className={`badge ${
              operationalStatus === 'UP'
                ? 'active'
                : operationalStatus === 'DOWN'
                  ? 'down'
                  : 'paused'
            }`}
          >
            {operationalStatus}
          </span>
        </div>
      </div>

      {error && (
        <div
          role="alert"
          className="error"
        >
          {error}{' '}

          <button
            disabled={loading}
            onClick={() => {
              setLoading(true)
              setError('')
              setRefresh(value => value + 1)
            }}
          >
            Reload
          </button>
        </div>
      )}

      {loading && !stats ? (
        <p
          role="status"
          className="panel"
        >
          Loading monitor details…
        </p>
      ) : (
        <>
          <section
            className="monitor-stats"
            aria-labelledby="stats-title"
          >
            <div className="section-heading">
              <div>
                <p className="eyebrow">
                  Last 24 hours
                </p>

                <h2 id="stats-title">
                  Performance
                </h2>
              </div>
            </div>

            <div className="metrics-grid">
              <article className="metric-card metric-up">
                <span className="metric-label">
                  Uptime
                </span>

                <strong className="metric-value">
                  {formatPercentage(
                    stats?.uptime_percentage ?? null,
                  )}
                </strong>
              </article>

              <article className="metric-card">
                <span className="metric-label">
                  Avg response
                </span>

                <strong className="metric-value">
                  {formatMilliseconds(
                    stats?.average_response_time_ms
                    ?? null,
                  )}
                </strong>
              </article>

              <article className="metric-card">
                <span className="metric-label">
                  Min response
                </span>

                <strong className="metric-value">
                  {formatMilliseconds(
                    stats?.minimum_response_time_ms
                    ?? null,
                  )}
                </strong>
              </article>

              <article className="metric-card">
                <span className="metric-label">
                  Max response
                </span>

                <strong className="metric-value">
                  {formatMilliseconds(
                    stats?.maximum_response_time_ms
                    ?? null,
                  )}
                </strong>
              </article>

              <article className="metric-card">
                <span className="metric-label">
                  Checks
                </span>

                <strong className="metric-value">
                  {stats?.total_checks ?? 0}
                </strong>
              </article>

              <article className="metric-card metric-up">
                <span className="metric-label">
                  Successful
                </span>

                <strong className="metric-value">
                  {stats?.successful_checks ?? 0}
                </strong>
              </article>

              <article
                className={`metric-card ${
                  (stats?.failed_checks ?? 0) > 0
                    ? 'metric-down'
                    : ''
                }`}
              >
                <span className="metric-label">
                  Failed
                </span>

                <strong className="metric-value">
                  {stats?.failed_checks ?? 0}
                </strong>
              </article>
            </div>
          </section>

          <section className="panel" aria-labelledby="monitor-incidents-title">
            <h2 id="monitor-incidents-title">Incidents</h2>
            <IncidentTable incidents={incidents?.items ?? []} />
            {incidents && <Pagination page={incidents} onOffset={setIncidentOffset} />}
          </section>

          <ResponseTimeChart
            checks={history?.items ?? []}
          />

          <section
            className="panel"
            aria-labelledby="history-title"
          >
            <div className="section-heading">
              <div>
                <p className="eyebrow">
                  Recent checks
                </p>

                <h2 id="history-title">
                  Check history
                </h2>
              </div>

              {history && history.total > 0 && (
                <span className="chart-unit">
                  Showing {history.items.length} of{' '}
                  {history.total}
                </span>
              )}
            </div>

            {!history || history.items.length === 0 ? (
              <p className="muted">
                No checks recorded yet.
              </p>
            ) : (
              <div className="table-wrap detail-history-table">
                <table>
                  <caption className="sr-only">
                    Monitor check history
                  </caption>

                  <thead>
                    <tr>
                      <th>Checked</th>
                      <th>Status</th>
                      <th>HTTP</th>
                      <th>Response</th>
                      <th>Error</th>
                    </tr>
                  </thead>

                  <tbody>
                    {history.items.map((check, index) => (
                      <tr
                        key={`${check.checked_at}-${index}`}
                      >
                        <td>
                          <time dateTime={check.checked_at}>
                            {new Date(
                              check.checked_at,
                            ).toLocaleString()}
                          </time>
                        </td>

                        <td>
                          <span
                            className={`badge ${
                              check.status === 'UP'
                                ? 'active'
                                : 'down'
                            }`}
                          >
                            {check.status}
                          </span>
                        </td>

                        <td>
                          {check.http_status_code ?? '—'}
                        </td>

                        <td>
                          {formatMilliseconds(
                            check.response_time_ms,
                          )}
                        </td>

                        <td>
                          {check.error_message ?? '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </>
  )
}