import { useState, type FormEvent } from 'react'
import { intervals, type Monitor, type MonitorInput } from './api'


export function MonitorForm({ monitor, busy, onSave, onCancel }: {
  monitor: Monitor | null; busy: boolean
  onSave: (input: MonitorInput) => Promise<void>; onCancel: () => void
}) {
  const [name, setName] = useState(monitor?.name ?? '')
  const [url, setUrl] = useState(monitor?.url ?? '')
  const [interval, setInterval] = useState(monitor?.interval_seconds ?? 60)
  const [timeout, setTimeout] = useState(monitor?.timeout_seconds ?? 10)
  const [active, setActive] = useState(monitor?.is_active ?? true)
  function submit(event: FormEvent) {
    event.preventDefault()
    void onSave({ name: name.trim(), url: url.trim(), method: 'GET', interval_seconds: interval, timeout_seconds: timeout, is_active: active })
  }
  return <section className="panel editor" aria-labelledby="editor-title">
    <h2 id="editor-title">{monitor ? 'Edit monitor' : 'Add monitor'}</h2>
    <form onSubmit={submit}>
      <fieldset disabled={busy}>
        <div className="form-grid">
          <label>Name<input autoFocus value={name} onChange={e => setName(e.target.value)} required pattern=".*\S.*" maxLength={120} placeholder="StatusWatch API" /></label>
          <label>URL<input type="url" value={url} onChange={e => setUrl(e.target.value)} required pattern="https?://.+" maxLength={2083} placeholder="https://example.com/health" /></label>
          <label>Method<select value="GET" disabled><option>GET</option></select></label>
          <label>Interval<select value={interval} onChange={e => setInterval(Number(e.target.value))}>{intervals.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>Timeout (seconds)<input type="number" min={1} max={30} step={1} required value={timeout} onChange={e => setTimeout(Number(e.target.value))} /></label>
          <label className="checkbox"><input type="checkbox" checked={active} onChange={e => setActive(e.target.checked)} />Active configuration</label>
        </div>
        <div className="actions"><button className="primary" type="submit">{busy ? 'Saving…' : 'Save monitor'}</button><button type="button" onClick={onCancel}>Cancel</button></div>
      </fieldset>
    </form>
  </section>
}
