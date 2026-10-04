import { useCallback, useEffect, useState } from 'react'
import './App.css'
import { AuthForm } from './AuthForm'
import { Monitors } from './Monitors'
import type { User } from './api'

type Status = 'checking' | 'online' | 'offline'

function App() {
  const [session, setSession] = useState<{ token: string; user: User } | null>(null)
  const [expired, setExpired] = useState(false)
  const onExpired = useCallback(() => { setSession(null); setExpired(true) }, [])
  const [status, setStatus] = useState<Status>('checking')

  useEffect(() => {
    let disposed = false
    let timer: ReturnType<typeof setTimeout>
    let controller: AbortController

    async function checkHealth() {
      controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 10_000)
      try {
        const response = await fetch('/api/health', {
          signal: controller.signal,
          cache: 'no-store',
        })
        const health = await response.json()
        if (!disposed) setStatus(response.ok && health.status === 'healthy' ? 'online' : 'offline')
      } catch {
        if (!disposed) setStatus('offline')
      } finally {
        clearTimeout(timeout)
        if (!disposed) timer = setTimeout(checkHealth, 15_000)
      }
    }

    void checkHealth()
    return () => {
      disposed = true
      clearTimeout(timer)
      controller?.abort()
    }
  }, [])

  return (
    <main className="splash">
      <header className="brand">
        <svg viewBox="0 0 32 32" aria-hidden="true">
          <path d="M3 17h6l4-10 6 19 4-9h6" />
        </svg>
        <span>STATUSWATCH</span>
      </header>
      {session && <div className="account"><span>{session.user.full_name}</span><button onClick={() => setSession(null)}>Sign out</button></div>}
      {expired && <p role="alert" className="error">Your session is no longer valid. Please sign in again.</p>}
      {session ? <Monitors token={session.token} onExpired={onExpired} /> : <AuthForm onLogin={(token, user) => { setSession({ token, user }); setExpired(false) }} />}
      <section className="status-card" aria-labelledby="status-title">
        <h2 id="status-title">System Status</h2>
        <p className={`status ${status}`} role="status" aria-live="polite">
          <span className="dot" aria-hidden="true" />
          {status === 'checking' ? 'Verificando API…' : status === 'online' ? 'API Online' : 'API Offline'}
        </p>
        <p className="status-note">
          {status === 'offline'
            ? 'API ou dependências indisponíveis. Tentaremos novamente em instantes.'
            : 'Disponibilidade da API e de suas dependências. Atualização automática.'}
        </p>
      </section>
      <footer><span>STATUSWATCH</span><span>v0.3.0</span></footer>
    </main>
  )
}

export default App
