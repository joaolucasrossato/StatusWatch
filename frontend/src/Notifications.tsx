import { useEffect, useRef, useState } from 'react'
import { ApiError, errorMessage, request, type ChannelInput, type DeliveryStatus, type EventType, type Monitor, type NotificationChannel, type NotificationDelivery, type Page } from './api'
import { Pagination, Timestamp } from './Incidents'
import { NotificationChannelForm } from './NotificationChannelForm'

export function Notifications({ monitor, token, onBack, onExpired }: {
  monitor: Monitor; token: string; onBack: () => void; onExpired: () => void
}) {
  const [channels, setChannels] = useState<NotificationChannel[]>([])
  const [deliveries, setDeliveries] = useState<Page<NotificationDelivery> | null>(null)
  const [editing, setEditing] = useState<NotificationChannel | null | undefined>(undefined)
  const [deleting, setDeleting] = useState<NotificationChannel | null>(null)
  const [status, setStatus] = useState<DeliveryStatus | ''>('')
  const [eventType, setEventType] = useState<EventType | ''>('')
  const [offset, setOffset] = useState(0)
  const [refresh, setRefresh] = useState(0)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const mounted = useRef(false)
  const mutation = useRef<AbortController | null>(null)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; mutation.current?.abort() }
  }, [])

  useEffect(() => {
    let disposed = false
    let timer: ReturnType<typeof setTimeout>
    const controller = new AbortController()
    async function load() {
      if (document.visibilityState === 'hidden' || busy || editing !== undefined || deleting) {
        timer = setTimeout(load, 30_000)
        return
      }
      try {
        const [channelData, deliveryData] = await Promise.all([
          request<NotificationChannel[]>(`/monitors/${monitor.id}/notification-channels`, token, 'GET', undefined, controller.signal),
          request<Page<NotificationDelivery>>(`/notification-deliveries?monitor_id=${monitor.id}&limit=50&offset=${offset}${status ? `&status=${status}` : ''}${eventType ? `&event_type=${eventType}` : ''}`, token, 'GET', undefined, controller.signal),
        ])
        if (!disposed) {
          setChannels(channelData); setDeliveries(deliveryData); setError('')
          if (offset > 0 && offset >= deliveryData.total) setOffset(Math.max(0, Math.ceil(deliveryData.total / 50) * 50 - 50))
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
  }, [monitor.id, token, onExpired, offset, status, eventType, refresh, busy, editing, deleting])

  async function mutate(path: string, method: string, body?: unknown) {
    if (busy) return
    setBusy(true); setError(''); setNotice('')
    const controller = new AbortController()
    mutation.current = controller
    try {
      await request(path, token, method, body, controller.signal)
      if (mounted.current) {
        setEditing(undefined); setDeleting(null); setNotice('Notification channel saved.'); setRefresh(value => value + 1)
      }
    } catch (failure) {
      if (mounted.current) {
        if (failure instanceof ApiError && [401, 403].includes(failure.status)) onExpired()
        else setError(errorMessage(failure))
      }
    } finally { if (mounted.current) setBusy(false) }
  }

  async function save(input: ChannelInput) {
    if (editing) {
      const { type: _type, target, ...flags } = input
      await mutate(`/notification-channels/${editing.id}`, 'PATCH', { ...flags, ...(target ? { target } : {}) })
    } else await mutate('/notification-channels', 'POST', { ...input, monitor_id: monitor.id })
  }
  const locked = busy || editing !== undefined || !!deleting
  return <>
    <div className="details-navigation"><button onClick={onBack} disabled={busy}>← Back to monitor details</button></div>
    <div className="page-heading"><div><p className="eyebrow">{monitor.name}</p><h1>Notifications</h1></div><div className="actions">
      <button disabled={locked || loading} onClick={() => { setLoading(true); setRefresh(value => value + 1) }}>Reload</button>
      <button className="primary" disabled={locked || loading} onClick={() => setEditing(null)}>Add channel</button>
    </div></div>
    <p className="version-note">Notifications follow incident transitions. Three consecutive DOWN checks open an incident; the first UP resolves it.</p>
    {error && <p role="alert" className="error">{error}</p>}
    {notice && <p role="status" className="success">{notice}</p>}
    {editing !== undefined && <NotificationChannelForm key={editing?.id ?? 'new'} channel={editing} busy={busy} onSave={save} onCancel={() => setEditing(undefined)} />}
    {deleting && <section className="panel" role="alertdialog" aria-label="Delete notification channel">
      <p>Delete {deleting.type} channel ({deleting.target}) and its delivery history?</p><div className="actions"><button className="danger" disabled={busy} onClick={() => void mutate(`/notification-channels/${deleting.id}`, 'DELETE')}>Confirm delete</button><button disabled={busy} onClick={() => setDeleting(null)}>Cancel</button></div>
    </section>}
    <section className="panel"><h2>Channels</h2>
      {loading && !deliveries ? <p role="status">Loading notifications…</p> : channels.length === 0 ? <p className="muted">No notification channels configured.</p> : <div className="table-wrap"><table>
        <thead><tr><th>Channel</th><th>Status</th><th>Events</th><th>Actions</th></tr></thead><tbody>{channels.map(channel => <tr key={channel.id}>
          <td>{channel.type}<span className="monitor-url">{channel.target}</span></td>
          <td><span className={`badge ${channel.is_active ? 'active' : 'paused'}`}>{channel.is_active ? 'Enabled' : 'Disabled'}</span></td>
          <td>{[channel.notify_on_open && 'Opened', channel.notify_on_resolved && 'Resolved'].filter(Boolean).join(', ') || 'None'}</td>
          <td><div className="actions"><button disabled={locked} onClick={() => setEditing(channel)}>Edit</button><button disabled={locked} onClick={() => void mutate(`/notification-channels/${channel.id}`, 'PATCH', { is_active: !channel.is_active })}>{channel.is_active ? 'Disable' : 'Enable'}</button><button disabled={locked} onClick={() => setDeleting(channel)}>Delete</button></div></td>
        </tr>)}</tbody>
      </table></div>}
    </section>
    <section className="panel"><h2>Delivery history</h2>
      <div className="form-grid"><label>Delivery status<select disabled={locked} value={status} onChange={event => { setStatus(event.target.value as DeliveryStatus | ''); setOffset(0); setDeliveries(null); setLoading(true) }}>
        <option value="">All</option>{(['PENDING', 'PROCESSING', 'SENT', 'FAILED'] as const).map(value => <option key={value}>{value}</option>)}
      </select></label><label>Event<select disabled={locked} value={eventType} onChange={event => { setEventType(event.target.value as EventType | ''); setOffset(0); setDeliveries(null); setLoading(true) }}>
        <option value="">All</option><option>INCIDENT_OPENED</option><option>INCIDENT_RESOLVED</option>
      </select></label></div>
      {loading && !deliveries ? <p role="status">Loading deliveries…</p> : deliveries && <>
        {deliveries.items.length === 0 ? <p className="muted">No deliveries recorded.</p> : <div className="table-wrap"><table>
          <thead><tr><th>Event</th><th>Channel</th><th>Status</th><th>Attempts</th><th>Created</th><th>Sent</th></tr></thead><tbody>{deliveries.items.map(delivery => {
            const channel = channels.find(item => item.id === delivery.channel_id)
            return <tr key={delivery.id}><td>{delivery.event_type}</td><td>{channel ? `${channel.type} · ${channel.target}` : delivery.channel_id}</td>
              <td><span className={`badge ${delivery.status === 'SENT' ? 'active' : delivery.status === 'FAILED' ? 'down' : 'paused'}`}>{delivery.status}</span>{delivery.last_error && <span className="check-details">{delivery.last_error}</span>}</td>
              <td>{delivery.attempt_count}</td><td><Timestamp value={delivery.created_at} /></td><td><Timestamp value={delivery.sent_at} /></td></tr>
          })}</tbody>
        </table></div>}
        <Pagination page={deliveries} disabled={loading || locked} onOffset={value => { setOffset(value); setDeliveries(null); setLoading(true) }} />
      </>}
    </section>
  </>
}
