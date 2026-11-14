import { useEffect, useState } from 'react'

const healthMessages = {
  checking: 'Consultando la API…',
  available: 'API disponible',
  unavailable: 'No se pudo conectar con la API',
} as const

type HealthStatus = keyof typeof healthMessages

export function App() {
  const [status, setStatus] = useState<HealthStatus>('checking')

  useEffect(() => {
    const request = new AbortController()
    const signal = AbortSignal.any([request.signal, AbortSignal.timeout(5000)])

    async function checkHealth() {
      try {
        const response = await fetch('/api/health', { signal })
        const payload: unknown = response.ok ? await response.json() : null
        const isHealthy =
          typeof payload === 'object' && payload !== null &&
          'status' in payload && payload.status === 'ok'
        setStatus(isHealthy ? 'available' : 'unavailable')
      } catch {
        if (!request.signal.aborted) setStatus('unavailable')
      }
    }

    void checkHealth()
    return () => request.abort()
  }, [])

  return (
    <>
      <header className="site-header">
        <div className="shell">Gestión de Edificios</div>
      </header>
      <main className="shell">
        <section className="status-card" aria-labelledby="status-title">
          <h1 id="status-title">Estado del servicio</h1>
          <p className="service-status" data-status={status} role="status">
            {healthMessages[status]}
          </p>
        </section>
      </main>
    </>
  )
}
