import { useCallback, useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import { ServiceCatalogPage } from './features/billing/ServiceCatalogPage'
import { InvoicePage } from './features/billing/InvoicePage'
import { StatementPage } from './features/collections/StatementPage'
import { CollectionsPage } from './features/collections/CollectionsPage'
import { ReceiptBatchesPage } from './features/collections/ReceiptBatchesPage'
import { PaymentReportsPage } from './features/collections/PaymentReportsPage'
import { LoginForm } from './features/identity/LoginForm'
import { getCurrentSession, type SessionUser } from './features/identity/api'
import { PropertyWorkspace } from './features/properties/PropertyWorkspace'
import { BuildingForm } from './features/properties/BuildingForm'
import { BuildingPage } from './features/properties/BuildingPage'
import { BuildingsList } from './features/properties/BuildingsList'
import { MyProperties, MyUnitPage } from './features/properties/OwnerProperties'
import { UnitPage, UnitsList, NewUnitPage } from './features/properties/UnitsPage'

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
      {auth.status !== 'ready' && <header className="site-header">
        <div className="shell">Gestión de Edificios</div>
      </header>}
      <div className={user ? 'authenticated-root' : auth.status === 'ready' ? 'public-main login-page' : 'shell public-main'} role={user ? undefined : 'main'}>
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
                <PropertyWorkspace user={user} onSignedOut={endSession} />
              ) : redirect}
            >
              <Route index element={<BuildingsList />} />
              <Route path="edificios/nuevo" element={<BuildingForm />} />
              <Route path="edificios/:buildingId" element={<BuildingPage key="detail" />} />
              <Route path="edificios/:buildingId/editar" element={<BuildingPage key="edit" editing />} />
              <Route path="edificios/:buildingId/servicios" element={<ServiceCatalogPage />} />
              <Route path="edificios/:buildingId/facturas" element={<InvoicePage />} />
              <Route path="edificios/:buildingId/reportes-de-pago" element={<PaymentReportsPage />} />
              <Route path="edificios/:buildingId/cobranzas" element={<CollectionsPage />} />
              <Route path="edificios/:buildingId/recibos-por-lote" element={<ReceiptBatchesPage />} />
              <Route path="edificios/:buildingId/facturas/:invoiceId" element={<InvoicePage />} />
              <Route path="edificios/:buildingId/unidades" element={<UnitsList />} />
              <Route path="edificios/:buildingId/unidades/nueva" element={<NewUnitPage />} />
              <Route path="edificios/:buildingId/unidades/:unitId" element={<UnitPage key="unit" />} />
              <Route path="edificios/:buildingId/unidades/:unitId/estado-de-cuenta" element={<StatementPage />} />
              <Route path="edificios/:buildingId/unidades/:unitId/editar" element={<UnitPage key="edit-unit" mode="unit" />} />
              <Route path="edificios/:buildingId/unidades/:unitId/propietario" element={<UnitPage key="edit-owner" mode="owner" />} />
            </Route>
            <Route
              path="/propietario"
              element={user?.role === 'Propietario' ? (
                <PropertyWorkspace user={user} onSignedOut={endSession} />
              ) : redirect}
            >
              <Route index element={<MyProperties />} />
              <Route path="unidades/:unitId" element={<MyUnitPage />} />
              <Route path="unidades/:unitId/estado-de-cuenta" element={<StatementPage />} />
            </Route>
            <Route path="*" element={redirect} />
          </Routes>
        )}
      </div>
    </>
  )
}
