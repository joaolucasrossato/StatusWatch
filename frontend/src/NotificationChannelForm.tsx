import { useState, type FormEvent } from 'react'
import type { ChannelInput, ChannelType, NotificationChannel } from './api'

export function NotificationChannelForm({ channel, busy, onSave, onCancel }: {
  channel: NotificationChannel | null; busy: boolean
  onSave: (input: ChannelInput) => Promise<void>; onCancel: () => void
}) {
  const [type, setType] = useState<ChannelType>(channel?.type ?? 'EMAIL')
  const [target, setTarget] = useState(channel?.target_redacted ? '' : channel?.target ?? '')
  const [active, setActive] = useState(channel?.is_active ?? true)
  const [opened, setOpened] = useState(channel?.notify_on_open ?? true)
  const [resolved, setResolved] = useState(channel?.notify_on_resolved ?? true)
  function submit(event: FormEvent) {
    event.preventDefault()
    void onSave({ type, target: target.trim(), is_active: active, notify_on_open: opened, notify_on_resolved: resolved })
  }
  return <form className="panel" onSubmit={submit} aria-label={channel ? 'Edit notification channel' : 'Add notification channel'}>
    <h2>{channel ? 'Edit channel' : 'Add channel'}</h2>
    <fieldset disabled={busy}>
      <div className="form-grid">
        <label>Channel type<select value={type} disabled={!!channel} onChange={event => { setType(event.target.value as ChannelType); setTarget('') }}><option>EMAIL</option><option>WEBHOOK</option></select></label>
        <label>{type === 'EMAIL' ? 'Email address' : 'Webhook URL'}<input type={type === 'EMAIL' ? 'email' : 'url'} value={target} required={!channel?.target_redacted} maxLength={2083} onChange={event => setTarget(event.target.value)} autoComplete="off" />
          {channel?.target_redacted && <span className="muted">Leave blank to keep the saved destination.</span>}
        </label>
      </div>
      <label className="checkbox"><input type="checkbox" checked={active} onChange={event => setActive(event.target.checked)} />Enabled</label>
      <label className="checkbox"><input type="checkbox" checked={opened} onChange={event => setOpened(event.target.checked)} />Incident opened</label>
      <label className="checkbox"><input type="checkbox" checked={resolved} onChange={event => setResolved(event.target.checked)} />Incident resolved</label>
      <div className="actions"><button className="primary" type="submit">{busy ? 'Saving…' : 'Save channel'}</button><button type="button" onClick={onCancel}>Cancel</button></div>
    </fieldset>
  </form>
}
