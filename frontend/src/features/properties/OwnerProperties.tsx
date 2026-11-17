import { useCallback } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'

import { PropertyRequestError } from './api'
import { listMyProperties, readMyUnit } from './ownerApi'
import { usePropertyQuery } from './usePropertyQuery'

function PortalLoadError({ error, retry }: { error: unknown; retry: () => void }) {
  if (error instanceof PropertyRequestError && error.status === 404) {
    return <p role="alert">No se encontró la unidad.</p>
  }
  if (error instanceof PropertyRequestError && error.status === 403) {
    return <p role="alert">Tu cuenta no tiene acceso a esta sección.</p>
  }
  return (
    <div>
      <p role="alert">No se pudo cargar la información.</p>
      <button type="button" onClick={retry}>Volver a intentar</button>
    </div>
  )
}

export function MyProperties() {
  const { query, retry } = usePropertyQuery(listMyProperties)

  return (
    <section className="building-page" aria-labelledby="my-properties-title">
      <h1 id="my-properties-title">Mis propiedades</h1>
      {query.status === 'loading' && <p role="status">Cargando tus unidades…</p>}
      {query.status === 'error' && <PortalLoadError error={query.error} retry={retry} />}
      {query.status === 'ready' && (query.data.length === 0 ? (
        <p className="building-surface">Todavía no tienes unidades asociadas.</p>
      ) : query.data.map((building) => (
        <section className="owner-building" key={building.id} aria-labelledby={`building-${building.id}`}>
          <h2 id={`building-${building.id}`}>{building.name}</h2>
          {building.address && <p>{building.address}</p>}
          <ul className="building-grid">
            {building.units.map((unit) => (
              <li key={unit.id} className="building-surface">
                <Link to={`unidades/${unit.id}`}>Unidad {unit.number}</Link>
                <p>{unit.area_sqm} m²</p>
              </li>
            ))}
          </ul>
        </section>
      )))}
    </section>
  )
}

function MyUnit({ unitId }: { unitId: string }) {
  const load = useCallback((signal: AbortSignal) => readMyUnit(unitId, signal), [unitId])
  const { query, retry } = usePropertyQuery(load)
  if (query.status === 'loading') return <p role="status">Cargando unidad…</p>
  if (query.status === 'error') return <PortalLoadError error={query.error} retry={retry} />

  const { building, payment_instructions: payment, number, area_sqm: area } = query.data
  const instructions = [
    { label: 'Banco', value: payment.bank_name },
    { label: 'Titular', value: payment.account_holder },
    { label: 'Número de cuenta', value: payment.account_number },
    { label: 'CCI', value: payment.cci },
    { label: 'Correo de contacto', value: payment.contact_email },
  ].filter(({ value }) => Boolean(value))

  return (
    <section className="building-page" aria-labelledby="my-unit-title">
      <div className="building-page-heading">
        <h1 id="my-unit-title">Unidad {number}</h1>
        <Link to="estado-de-cuenta">Estado de cuenta</Link>
      </div>
      <div className="building-grid">
        <section className="building-surface" aria-labelledby="my-unit-information">
          <h2 id="my-unit-information">Datos de la unidad</h2>
          <dl className="building-details">
            <div><dt>Edificio</dt><dd>{building.name}</dd></div>
            {building.address && <div><dt>Dirección</dt><dd>{building.address}</dd></div>}
            <div><dt>Área</dt><dd>{area} m²</dd></div>
          </dl>
        </section>
        <section className="building-surface" aria-labelledby="my-unit-payment">
          <h2 id="my-unit-payment">Instrucciones de pago</h2>
          {instructions.length === 0 ? (
            <p>Aún no hay instrucciones de pago para este edificio.</p>
          ) : (
            <dl className="building-details">
              {instructions.map(({ label, value }) => (
                <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
              ))}
            </dl>
          )}
        </section>
      </div>
    </section>
  )
}

export function MyUnitPage() {
  const { unitId } = useParams()
  return unitId ? <MyUnit key={unitId} unitId={unitId} /> : <Navigate to="/propietario" replace />
}
