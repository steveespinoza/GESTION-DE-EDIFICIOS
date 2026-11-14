import { useCallback, useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import { LoginForm } from './features/identity/LoginForm'
import { RolePanel } from './features/identity/RolePanel'
import { getCurrentSession, type SessionUser } from './features/identity/api'
import { AdminWorkspace } from './features/properties/AdminWorkspace'
import { BuildingForm } from './features/properties/BuildingForm'
import { BuildingPage } from './features/properties/BuildingPage'
import { BuildingsList } from './features/properties/BuildingsList'

type AuthState =
  | { status: 'loading' | 'unavailable' }
  | { status: 'ready'; user: SessionUser | null }

export function App() {
  const [auth, setAuth] = useState<AuthState>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const user = auth.status === 'ready' ? auth.user : null

  useEffect(() => {
    const request = new AbortController()
    void getCurrentSession(request.signal).then(
      (session) => {
        if (!request.signal.aborted) setAuth({ status: 'ready', user: session })
      },
      () => {
        if (!request.signal.aborted) setAuth({ status: 'unavailable' })
      },
    )
    return () => request.abort()
  }, [attempt])

  const endSession = useCallback(() => setAuth({ status: 'ready', user: null }), [])

  useEffect(() => {
    if (!user) return
    const remaining = Date.parse(user.expires_at) - Date.now()
    const timer = window.setTimeout(endSession, Math.max(remaining, 0))
    return () => window.clearTimeout(timer)
  }, [user, endSession])

  function retrySession() {
    setAuth({ status: 'loading' })
    setAttempt((previous) => previous + 1)
  }

  const home = user?.role === 'SuperAdmin' ? '/admin' : '/propietario'
  const redirect = <Navigate to={user ? home : '/login'} replace />

  return (
    <>
      <header className="site-header">
        <div className="shell">Gestión de Edificios</div>
      </header>
      <main className="shell">
        {auth.status === 'loading' && <p role="status">Comprobando la sesión…</p>}
        {auth.status === 'unavailable' && (
          <section className="status-card" aria-labelledby="connection-title">
            <h1 id="connection-title">No se pudo comprobar la sesión</h1>
            <button onClick={retrySession}>Volver a intentar</button>
          </section>
        )}
        {auth.status === 'ready' && (
          <Routes>
            <Route
              path="/login"
              element={user ? redirect : (
                <LoginForm onSignedIn={(session) => setAuth({ status: 'ready', user: session })} />
              )}
            />
            <Route
              path="/admin"
              element={user?.role === 'SuperAdmin' ? (
                <AdminWorkspace onSignedOut={endSession} />
              ) : redirect}
            >
              <Route index element={<BuildingsList />} />
              <Route path="edificios/nuevo" element={<BuildingForm />} />
              <Route path="edificios/:buildingId" element={<BuildingPage key="detail" />} />
              <Route path="edificios/:buildingId/editar" element={<BuildingPage key="edit" editing />} />
            </Route>
            <Route
              path="/propietario"
              element={user?.role === 'Propietario' ? (
                <RolePanel role="Propietario" onSignedOut={endSession} />
              ) : redirect}
            />
            <Route path="*" element={redirect} />
          </Routes>
        )}
      </main>
    </>
  )
}
