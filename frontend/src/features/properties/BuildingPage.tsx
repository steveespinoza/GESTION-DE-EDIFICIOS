import { useCallback } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'

import { BuildingForm } from './BuildingForm'
import { buildingErrorMessage, PropertyRequestError, readBuilding } from './api'
import { usePropertyQuery } from './usePropertyQuery'

function BuildingRecord({ id, editing }: { id: string; editing: boolean }) {
  const load = useCallback((signal: AbortSignal) => readBuilding(id, signal), [id])
  const { query, retry } = usePropertyQuery(load)

  if (query.status === 'loading') return <p role="status">Cargando edificio…</p>
  if (query.status === 'error') {
    const missing = query.error instanceof PropertyRequestError && query.error.status === 404
    return (
      <div>
        <p role="alert">{buildingErrorMessage(query.error, 'No se pudo cargar el edificio.')}</p>
        {!missing && <button type="button" onClick={retry}>Volver a intentar</button>}
      </div>
    )
  }
  const building = query.data
  if (editing) return <BuildingForm building={building} />

  const paymentDetails = [
    { label: 'Banco', value: building.bank_name },
    { label: 'Titular', value: building.account_holder },
    { label: 'Número de cuenta', value: building.account_number },
    { label: 'CCI', value: building.cci },
    { label: 'Correo de contacto', value: building.contact_email },
  ]
  return (
    <section className="building-page" aria-labelledby="building-title">
      <div className="building-page-heading">
        <h1 id="building-title">{building.name}</h1>
        <div className="building-form-actions">
          <Link className="button-link" to="unidades">Unidades</Link>
          <Link to="servicios">Servicios</Link>
          <Link to="editar">Editar edificio</Link>
        </div>
      </div>
      <div className="building-grid">
        <section className="building-surface" aria-labelledby="general-title">
          <h2 id="general-title">Datos generales</h2>
          <dl className="building-details">
            <div><dt>Dirección</dt><dd>{building.address ?? '—'}</dd></div>
            <div><dt>Capacidad de unidades</dt><dd>{building.total_units}</dd></div>
          </dl>
        </section>
        <section className="building-surface" aria-labelledby="payment-title">
          <h2 id="payment-title">Instrucciones de pago</h2>
          <dl className="building-details">
            {paymentDetails.map(({ label, value }) => (
              <div key={label}><dt>{label}</dt><dd>{value ?? '—'}</dd></div>
            ))}
          </dl>
        </section>
      </div>
    </section>
  )
}

export function BuildingPage({ editing = false }: { editing?: boolean }) {
  const { buildingId } = useParams()
  return buildingId
    ? <BuildingRecord key={buildingId} id={buildingId} editing={editing} />
    : <Navigate to="/admin" replace />
}
