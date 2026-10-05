import { useEffect, useState } from 'react'
import {
  ApiError,
  errorMessage,
  intervals,
  request,
  type DashboardSummary as DashboardSummaryData,
  type Monitor,
  type MonitorInput,
} from './api'
import { DashboardSummary } from './DashboardSummary'
import { MonitorDetails } from './MonitorDetails'
import { Incidents } from './Incidents'
import { MonitorForm } from './MonitorForm'

export function Monitors({
  token,
  onExpired,
}: {
  token: string
  onExpired: () => void
}) {
  const [page, setPage] = useState<'monitors' | 'incidents'>('monitors')
  const [monitors, setMonitors] = useState<Monitor[]>([])
  const [summary, setSummary] =
    useState<DashboardSummaryData | null>(null)
  const [selectedMonitor, setSelectedMonitor] =
    useState<Monitor | null>(null)

  const [loading, setLoading] = useState(true)
  const [loaded, setLoaded] = useState(false)
  const [refresh, setRefresh] = useState(0)

  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const [editing, setEditing] =
    useState<Monitor | null | undefined>(undefined)

  const [deleting, setDeleting] =
    useState<Monitor | null>(null)

  const [notice, setNotice] = useState('')

  useEffect(() => {
    let disposed = false
    let timer: ReturnType<typeof setTimeout>

    async function reload() {
      if (
        document.visibilityState !== 'hidden'
        && !busy
        && editing === undefined
        && !deleting
        && !selectedMonitor
        && page === 'monitors'
      ) {
        try {
          const [monitorData, summaryData] =
            await Promise.all([
              request<Monitor[]>(
                '/monitors',
                token,
              ),
              request<DashboardSummaryData>(
                '/dashboard/summary',
                token,
              ),
            ])

          if (!disposed) {
            setMonitors(monitorData)
            setSummary(summaryData)
            setLoaded(true)
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
          }
        }
      }

      if (!disposed) {
        timer = setTimeout(
          reload,
          30_000,
        )
      }
    }

    void reload()

    return () => {
      disposed = true
      clearTimeout(timer)
    }
  }, [
    token,
    refresh,
    onExpired,
    busy,
    editing,
    deleting,
    selectedMonitor,
    page,
  ])

  async function mutate(
    action: () => Promise<void>,
    message: string,
  ) {
    setBusy(true)
    setError('')
    setNotice('')

    try {
      await action()

      setNotice(message)

      /*
       * Atualiza novamente os monitores e o resumo.
       *
       * Criar, editar, pausar, ativar ou excluir um monitor
       * pode alterar os números apresentados no dashboard.
       */
      setRefresh(value => value + 1)
    } catch (failure) {
      if (
        failure instanceof ApiError
        && [401, 403].includes(failure.status)
      ) {
        onExpired()
      } else {
        setError(errorMessage(failure))
      }
    } finally {
      setBusy(false)
    }
  }

  async function save(input: MonitorInput) {
    await mutate(
      async () => {
        const updated = await request<Monitor>(
          editing
            ? `/monitors/${editing.id}`
            : '/monitors',
          token,
          editing ? 'PATCH' : 'POST',
          input,
        )

        setMonitors(current =>
          editing
            ? current.map(item =>
                item.id === updated.id
                  ? updated
                  : item,
              )
            : [updated, ...current],
        )

        setEditing(undefined)
      },
      'Monitor saved.',
    )
  }

  function startCreating() {
    setEditing(null)
    setDeleting(null)
    setSelectedMonitor(null)
    setError('')
    setNotice('')
  }

  function startEditing(monitor: Monitor) {
    setEditing(monitor)
    setDeleting(null)
    setSelectedMonitor(null)
    setError('')
    setNotice('')
  }

  function startDeleting(monitor: Monitor) {
    setDeleting(monitor)
    setEditing(undefined)
    setSelectedMonitor(null)
    setError('')
    setNotice('')
  }

  function openDetails(monitor: Monitor) {
    setSelectedMonitor(monitor)
    setEditing(undefined)
    setDeleting(null)
    setError('')
    setNotice('')
  }

  if (page === 'incidents') {
    return <Incidents token={token} monitors={monitors} onExpired={onExpired} onBack={() => setPage('monitors')} />
  }

  if (selectedMonitor) {
    const currentMonitor =
      monitors.find(
        item =>
          item.id === selectedMonitor.id,
      ) ?? selectedMonitor

    return (
      <MonitorDetails
        monitor={currentMonitor}
        token={token}
        onExpired={onExpired}
        onBack={() =>
          setSelectedMonitor(null)
        }
      />
    )
  }

  return (
    <>
      <nav className="details-navigation actions" aria-label="Monitoring navigation">
        <button aria-current="page">Monitors</button>
        <button disabled={busy || editing !== undefined || !!deleting} onClick={() => setPage('incidents')}>Incidents</button>
      </nav>
      <div className="page-heading">
        <div>
          <p className="eyebrow">
            Monitor management
          </p>

          <h1>
            My monitors
          </h1>
        </div>

        <button
          className="primary"
          disabled={
            busy
            || editing !== undefined
            || !loaded
          }
          onClick={startCreating}
        >
          + Add monitor
        </button>
      </div>

      <p className="version-note">
        HTTP checks refresh every 30 seconds while this page
        is visible. Active/Paused controls monitoring;
        UP/DOWN is the latest result.
      </p>

      <DashboardSummary
        summary={summary}
        loading={loading}
      />

      {error && (
        <div
          role="alert"
          className="error"
        >
          {error}{' '}

          <button
            disabled={
              busy || loading
            }
            onClick={() => {
              setLoading(true)
              setError('')
              setRefresh(
                value => value + 1,
              )
            }}
          >
            Reload
          </button>
        </div>
      )}

      {notice && (
        <p
          role="status"
          className="success"
        >
          {notice}
        </p>
      )}

      {editing !== undefined && (
        <MonitorForm
          key={
            editing?.id ?? 'new'
          }
          monitor={editing}
          busy={busy}
          onSave={save}
          onCancel={() => {
            setEditing(undefined)
            setError('')
          }}
        />
      )}

      {deleting && (
        <section
          className="panel delete-confirm"
          aria-labelledby="delete-title"
        >
          <h2 id="delete-title">
            Delete “{deleting.name}”?
          </h2>

          <p>
            This permanently removes this monitor
            and its checks.
          </p>

          <div className="actions">
            <button
              className="danger"
              disabled={busy}
              onClick={() =>
                void mutate(
                  async () => {
                    await request(
                      `/monitors/${deleting.id}`,
                      token,
                      'DELETE',
                    )

                    setMonitors(
                      current =>
                        current.filter(
                          item =>
                            item.id
                            !== deleting.id,
                        ),
                    )

                    setDeleting(null)
                  },
                  'Monitor deleted.',
                )
              }
            >
              {busy
                ? 'Deleting…'
                : 'Confirm delete'}
            </button>

            <button
              disabled={busy}
              onClick={() =>
                setDeleting(null)
              }
            >
              Cancel
            </button>
          </div>
        </section>
      )}

      {loading && !loaded ? (
        <p
          role="status"
          className="panel"
        >
          Loading monitors…
        </p>
      ) : loaded
        && monitors.length === 0 ? (
        <section className="panel empty">
          <span
            className="empty-icon"
            aria-hidden="true"
          >
            ＋
          </span>

          <h2>
            No monitors yet
          </h2>

          <p className="muted">
            Add a service URL to start building
            your monitoring workspace.
          </p>

          <button
            disabled={
              editing !== undefined
            }
            onClick={
              startCreating
            }
          >
            Add your first monitor
          </button>
        </section>
      ) : loaded ? (
        <div className="panel table-wrap">
          <table>
            <caption className="sr-only">
              Your monitor configurations
            </caption>

            <thead>
              <tr>
                <th>
                  Name / URL
                </th>

                <th>
                  Method
                </th>

                <th>
                  Interval
                </th>

                <th>
                  Timeout
                </th>

                <th>
                  Monitoring
                </th>

                <th>
                  Operational status
                </th>

                <th>
                  Actions
                </th>
              </tr>
            </thead>

            <tbody>
              {monitors.map(
                monitor => (
                  <tr key={monitor.id}>
                    <td>
                      <strong>
                        {monitor.name}
                      </strong>

                      <span className="monitor-url">
                        {monitor.url}
                      </span>
                    </td>

                    <td>
                      {monitor.method}
                    </td>

                    <td>
                      {
                        intervals.find(
                          ([value]) =>
                            value
                            === monitor.interval_seconds,
                        )?.[1]
                      }
                    </td>

                    <td>
                      {
                        monitor.timeout_seconds
                      }
                      s
                    </td>

                    <td>
                      <span
                        className={`badge ${
                          monitor.is_active
                            ? 'active'
                            : 'paused'
                        }`}
                      >
                        {
                          monitor.is_active
                            ? 'Active'
                            : 'Paused'
                        }
                      </span>
                    </td>

                    <td>
                      <span
                        className={`badge ${
                          monitor.latest_check
                            ?.status
                          === 'UP'
                            ? 'active'
                            : monitor.latest_check
                                  ?.status
                                === 'DOWN'
                              ? 'down'
                              : 'paused'
                        }`}
                      >
                        {
                          monitor.latest_check
                            ?.status
                          ?? 'Pending'
                        }
                      </span>

                      {monitor.latest_check && (
                        <div className="check-details">
                          {monitor.latest_check
                            .http_status_code
                            !== null && (
                            <span>
                              HTTP:{' '}
                              {
                                monitor
                                  .latest_check
                                  .http_status_code
                              }
                            </span>
                          )}

                          {monitor.latest_check
                            .response_time_ms
                            !== null && (
                            <span>
                              Response:{' '}
                              {
                                monitor
                                  .latest_check
                                  .response_time_ms
                              }{' '}
                              ms
                            </span>
                          )}

                          {monitor.latest_check
                            .error_message && (
                            <span>
                              {
                                monitor
                                  .latest_check
                                  .error_message
                              }
                            </span>
                          )}

                          <span>
                            Last check:{' '}

                            <time
                              dateTime={
                                monitor
                                  .latest_check
                                  .checked_at
                              }
                            >
                              {new Date(
                                monitor
                                  .latest_check
                                  .checked_at,
                              ).toLocaleString()}
                            </time>
                          </span>

                          {!monitor.is_active && (
                            <span>
                              Monitoring paused
                              {' — '}
                              last result retained
                            </span>
                          )}
                        </div>
                      )}
                    </td>

                    <td>
                      <div className="actions">
                        <button
                          aria-label={
                            `View details for ${monitor.name}`
                          }
                          disabled={
                            busy
                            || editing
                              !== undefined
                            || !!deleting
                          }
                          onClick={() =>
                            openDetails(
                              monitor,
                            )
                          }
                        >
                          View details
                        </button>

                        <button
                          aria-label={
                            `Edit ${monitor.name}`
                          }
                          disabled={
                            busy
                            || editing
                              !== undefined
                            || !!deleting
                          }
                          onClick={() =>
                            startEditing(
                              monitor,
                            )
                          }
                        >
                          Edit
                        </button>

                        <button
                          aria-label={`${
                            monitor.is_active
                              ? 'Pause'
                              : 'Activate'
                          } ${monitor.name}`}
                          disabled={
                            busy
                            || editing
                              !== undefined
                            || !!deleting
                          }
                          onClick={() =>
                            void mutate(
                              async () => {
                                const updated =
                                  await request<Monitor>(
                                    `/monitors/${monitor.id}`,
                                    token,
                                    'PATCH',
                                    {
                                      is_active:
                                        !monitor.is_active,
                                    },
                                  )

                                setMonitors(
                                  current =>
                                    current.map(
                                      item =>
                                        item.id
                                        === updated.id
                                          ? updated
                                          : item,
                                    ),
                                )
                              },
                              'Configuration updated.',
                            )
                          }
                        >
                          {
                            monitor.is_active
                              ? 'Pause'
                              : 'Activate'
                          }
                        </button>

                        <button
                          className="danger-text"
                          aria-label={
                            `Delete ${monitor.name}`
                          }
                          disabled={
                            busy
                            || editing
                              !== undefined
                            || !!deleting
                          }
                          onClick={() =>
                            startDeleting(
                              monitor,
                            )
                          }
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
      ) : null}
    </>
  )
}