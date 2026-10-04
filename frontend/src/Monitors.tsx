import { useEffect, useState } from 'react'
import { ApiError, errorMessage, intervals, request, type Monitor, type MonitorInput } from './api'
import { MonitorForm } from './MonitorForm'

export function Monitors({ token, onExpired }: { token: string; onExpired: () => void }) {
  const [monitors, setMonitors] = useState<Monitor[]>([])
  const [loading, setLoading] = useState(true)
  const [loaded, setLoaded] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState<Monitor | null | undefined>(undefined)
  const [deleting, setDeleting] = useState<Monitor | null>(null)
  const [notice, setNotice] = useState('')

  useEffect(() => {
    let disposed = false
    request<Monitor[]>('/monitors', token).then(data => {
      if (!disposed) { setMonitors(data); setLoaded(true) }
    }).catch(failure => {
      if (!disposed) {
        if (failure instanceof ApiError && [401, 403].includes(failure.status)) onExpired()
        else setError(errorMessage(failure))
      }
    }).finally(() => { if (!disposed) setLoading(false) })
    return () => { disposed = true }
  }, [token, refresh, onExpired])

  async function mutate(action: () => Promise<void>, message: string) {
    setBusy(true); setError(''); setNotice('')
    try { await action(); setNotice(message) }
    catch (failure) {
      if (failure instanceof ApiError && [401, 403].includes(failure.status)) onExpired()
      else setError(errorMessage(failure))
    } finally { setBusy(false) }
  }
  async function save(input: MonitorInput) {
    await mutate(async () => {
      const updated = await request<Monitor>(editing ? `/monitors/${editing.id}` : '/monitors', token, editing ? 'PATCH' : 'POST', input)
      setMonitors(current => editing ? current.map(item => item.id === updated.id ? updated : item) : [updated, ...current])
      setEditing(undefined)
    }, 'Monitor saved.')
  }
  return <>
    <div className="page-heading"><div><p className="eyebrow">Monitor management</p><h1>My monitors</h1></div>
      <button className="primary" disabled={busy || editing !== undefined || !loaded} onClick={() => { setEditing(null); setDeleting(null); setError('') }}>+ Add monitor</button></div>
    <p className="version-note">Configure what matters. HTTP checks arrive in v0.4. Active and Paused describe configuration only.</p>
    {error && <div role="alert" className="error">{error} <button disabled={busy || loading} onClick={() => { setLoading(true); setError(''); setRefresh(value => value + 1) }}>Reload list</button></div>}
    {notice && <p role="status" className="success">{notice}</p>}
    {editing !== undefined && <MonitorForm key={editing?.id ?? 'new'} monitor={editing} busy={busy} onSave={save} onCancel={() => { setEditing(undefined); setError('') }} />}
    {deleting && <section className="panel delete-confirm" aria-labelledby="delete-title">
      <h2 id="delete-title">Delete “{deleting.name}”?</h2><p>This permanently removes this monitor configuration.</p>
      <div className="actions"><button className="danger" disabled={busy} onClick={() => void mutate(async () => {
        await request(`/monitors/${deleting.id}`, token, 'DELETE')
        setMonitors(current => current.filter(item => item.id !== deleting.id)); setDeleting(null)
      }, 'Monitor deleted.')}>{busy ? 'Deleting…' : 'Confirm delete'}</button><button disabled={busy} onClick={() => setDeleting(null)}>Cancel</button></div>
    </section>}
    {loading ? <p role="status" className="panel">Loading monitors…</p> : loaded && monitors.length === 0 ? <section className="panel empty">
      <span className="empty-icon" aria-hidden="true">＋</span><h2>No monitors yet</h2><p className="muted">Add a service URL to start building your monitoring workspace.</p>
      <button disabled={editing !== undefined} onClick={() => setEditing(null)}>Add your first monitor</button>
    </section> : loaded && <div className="panel table-wrap"><table><caption className="sr-only">Your monitor configurations</caption><thead><tr><th>Name / URL</th><th>Method</th><th>Interval</th><th>Timeout</th><th>State</th><th>Actions</th></tr></thead><tbody>
      {monitors.map(monitor => <tr key={monitor.id}>
        <td><strong>{monitor.name}</strong><span className="monitor-url">{monitor.url}</span></td><td>GET</td>
        <td>{intervals.find(([value]) => value === monitor.interval_seconds)?.[1]}</td><td>{monitor.timeout_seconds}s</td>
        <td><span className={`badge ${monitor.is_active ? 'active' : 'paused'}`}>{monitor.is_active ? 'Active' : 'Paused'}</span></td>
        <td><div className="actions"><button aria-label={`Edit ${monitor.name}`} disabled={busy || editing !== undefined || !!deleting} onClick={() => { setEditing(monitor); setError('') }}>Edit</button>
          <button aria-label={`${monitor.is_active ? 'Pause' : 'Activate'} ${monitor.name}`} disabled={busy || editing !== undefined || !!deleting} onClick={() => void mutate(async () => {
            const updated = await request<Monitor>(`/monitors/${monitor.id}`, token, 'PATCH', { is_active: !monitor.is_active })
            setMonitors(current => current.map(item => item.id === updated.id ? updated : item))
          }, 'Configuration updated.')}>{monitor.is_active ? 'Pause' : 'Activate'}</button>
          <button className="danger-text" aria-label={`Delete ${monitor.name}`} disabled={busy || editing !== undefined || !!deleting} onClick={() => { setDeleting(monitor); setError('') }}>Delete</button></div></td>
      </tr>)}
    </tbody></table></div>}
  </>
}
