import { useState, type FormEvent } from 'react'
import { errorMessage, request, type User } from './api'

export function AuthForm({ onLogin }: { onLogin: (token: string, user: User) => void }) {
  const [register, setRegister] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const credentials = { email: String(data.get('email')), password: String(data.get('password')) }
    setBusy(true); setError(''); setNotice('')
    try {
      if (register) {
        await request('/auth/register', undefined, 'POST', { ...credentials, full_name: data.get('full_name') })
        setRegister(false)
        setNotice('Account created. Sign in with your email and password.')
      } else {
        const result = await request<{ access_token: string }>('/auth/login', undefined, 'POST', credentials)
        const user = await request<User>('/auth/me', result.access_token)
        onLogin(result.access_token, user)
      }
    } catch (failure) { setError(errorMessage(failure)) }
    finally { setBusy(false) }
  }
  return <section className="panel auth-panel">
    <p className="eyebrow">Your reliability workspace</p>
    <h1>{register ? 'Create your account' : 'Welcome back'}</h1>
    <p className="muted">Keep the services you care about in one place.</p>
    <form onSubmit={submit}>
      <fieldset disabled={busy}>
        {register && <label>Full name<input name="full_name" autoComplete="name" minLength={2} maxLength={120} required /></label>}
        <label>Email<input name="email" type="email" autoComplete="username" required /></label>
        <label>Password<input name="password" type="password" autoComplete={register ? 'new-password' : 'current-password'} minLength={register ? 12 : 1} maxLength={128} required /></label>
        {register && <small className="muted">Use at least 12 characters.</small>}
        <button className="primary" type="submit">{busy ? 'Please wait…' : register ? 'Create account' : 'Sign in'}</button>
      </fieldset>
      {error && <p role="alert" className="error">{error}</p>}
      {notice && <p role="status">{notice}</p>}
    </form>
    <button className="text-button" disabled={busy} onClick={() => { setRegister(!register); setError(''); setNotice('') }}>
      {register ? 'Already have an account? Sign in' : 'New to StatusWatch? Create an account'}
    </button>
  </section>
}
