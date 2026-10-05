import { useEffect, useState } from 'react'
import { ApiError, errorMessage, request, type Incident, type IncidentList, type IncidentStatus, type Monitor, type Page } from './api'

export function Timestamp({ value }: { value: string | null }) {
  return value ? <time dateTime={value}>{new Date(value).toLocaleString()}</time> : <>—</>
}

export function Pagination({ page, onOffset, disabled = false }: {
  page: Page<unknown>; onOffset: (offset: number) => void; disabled?: boolean
}) {
  return <div className="pagination actions" aria-label="Pagination">
    <button disabled={disabled || page.offset === 0} onClick={() => onOffset(Math.max(0, page.offset - page.limit))}>Previous</button>
    <span role="status">Showing {page.items.length ? page.offset + 1 : 0}-{page.offset + page.items.length} of {page.total}</span>
    <button disabled={disabled || page.offset + page.limit >= page.total} onClick={() => onOffset(page.offset + page.limit)}>Next</button>
  </div>
}

export function IncidentTable({ incidents, monitors }: { incidents: Incident[]; monitors?: Monitor[] }) {
  if (!incidents.length) return <p className="muted">No incidents recorded.</p>
  return <div className="table-wrap"><table>
    <caption className="sr-only">Incident history</caption>
    <thead><tr>{monitors && <th>Monitor</th>}<th>Status</th><th>Started</th><th>Opened</th><th>Resolved</th></tr></thead>
    <tbody>{incidents.map(incident => <tr key={incident.id}>
      {monitors && <td>{monitors.find(monitor => monitor.id === incident.monitor_id)?.name ?? incident.monitor_id}</td>}
      <td><span className={`badge ${incident.status === 'OPEN' ? 'down' : 'active'}`}>{incident.status}</span></td>
      <td><Timestamp value={incident.started_at} /></td><td><Timestamp value={incident.opened_at} /></td><td><Timestamp value={incident.resolved_at} /></td>
    </tr>)}</tbody>
  </table></div>
}

export function Incidents({ token, monitors, onBack, onExpired }: {
  token: string; monitors: Monitor[]; onBack: () => void; onExpired: () => void
}) {
  const [status, setStatus] = useState<IncidentStatus | ''>('')
  const [offset, setOffset] = useState(0)
  const [page, setPage] = useState<IncidentList | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    let disposed = false
    let timer: ReturnType<typeof setTimeout>
    const controller = new AbortController()
    async function load() {
      if (document.visibilityState === 'hidden') {
        timer = setTimeout(load, 30_000)
        return
      }
      try {
        const data = await request<IncidentList>(`/incidents?limit=50&offset=${offset}${status ? `&status=${status}` : ''}`, token, 'GET', undefined, controller.signal)
        if (!disposed) {
          if (offset > 0 && offset >= data.total) setOffset(Math.max(0, Math.ceil(data.total / 50) * 50 - 50))
          setPage(data)
          setError('')
        }
      } catch (failure) {
        if (!disposed) {
          if (failure instanceof ApiError && [401, 403].includes(failure.status)) onExpired()
          else setError(errorMessage(failure))
        }
      } finally {
        if (!disposed) { setLoading(false); timer = setTimeout(load, 30_000) }
      }
    }
    void load()
    return () => { disposed = true; controller.abort(); clearTimeout(timer) }
  }, [token, onExpired, offset, status, refresh])

  return <>
    <nav className="details-navigation actions" aria-label="Monitoring navigation"><button onClick={onBack}>Monitors</button><button aria-current="page">Incidents</button></nav>
    <div className="page-heading"><h1>Incidents</h1><button disabled={loading} onClick={() => { setLoading(true); setRefresh(value => value + 1) }}>Reload</button></div>
    <section className="panel">
      <label>Filter by status<select value={status} onChange={event => { setStatus(event.target.value as IncidentStatus | ''); setOffset(0); setPage(null); setLoading(true) }}>
        <option value="">All</option><option value="OPEN">OPEN</option><option value="RESOLVED">RESOLVED</option>
      </select></label>
      {error && <p className="error" role="alert">{error}</p>}
      {loading && !page ? <p role="status">Loading incidents…</p> : page && <>
        <IncidentTable incidents={page.items} monitors={monitors} />
        <Pagination page={page} disabled={loading} onOffset={value => { setOffset(value); setPage(null); setLoading(true) }} />
      </>}
    </section>
  </>
}
