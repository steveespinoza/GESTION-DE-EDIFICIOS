import { useEffect, useState } from 'react'

import { getRoleSession, logout, SessionRequestError, type Role, type SessionUser } from './api'

interface RolePanelProps {
  role: Role
  onSignedOut: () => void
}

export function RolePanel({ role, onSignedOut }: RolePanelProps) {
  const [user, setUser] = useState<SessionUser | null>(null)
  const [error, setError] = useState('')
  const [signingOut, setSigningOut] = useState(false)

  useEffect(() => {
    const request = new AbortController()
    void getRoleSession(role, request.signal).then(
      (session) => {
        if (request.signal.aborted) return
        if (session) setUser(session)
        else onSignedOut()
      },
      (issue: unknown) => {
        if (request.signal.aborted) return
        setError(issue instanceof SessionRequestError && issue.status === 403
          ? 'Tu cuenta no tiene acceso a esta sección.'
          : 'No se pudo cargar el panel.')
      },
    )
    return () => request.abort()
  }, [role, onSignedOut])

  async function handleSignOut() {
    setSigningOut(true)
    setError('')
    try {
      await logout()
      onSignedOut()
    } catch {
      setError('No se pudo cerrar la sesión. Vuelve a intentarlo.')
    } finally {
      setSigningOut(false)
    }
  }

  return (
    <section className="status-card" aria-labelledby="panel-title">
      <h1 id="panel-title">{role === 'SuperAdmin' ? 'Panel de administración' : 'Mis propiedades'}</h1>
      {user && <p>Sesión iniciada como {user.full_name}.</p>}
      {!user && !error && <p role="status">Comprobando el acceso…</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      <button onClick={handleSignOut} disabled={signingOut}>
        {signingOut ? 'Cerrando sesión…' : 'Cerrar sesión'}
      </button>
    </section>
  )
}
