import { useCallback, useState, type FormEvent } from 'react'
import { Link, Navigate, useOutletContext, useParams } from 'react-router-dom'

import { PropertyRequestError, readBuilding } from '../properties/api'
import { usePropertyQuery } from '../properties/usePropertyQuery'
import { createService, listServices, type CalculationType } from './api'

const calculationLabels: Record<CalculationType, string> = {
  LINEAR: 'Lineal',
  METERED: 'Por consumo medido',
}

function saveError(error: unknown) {
  if (error instanceof PropertyRequestError) {
    if (error.status === 409 && error.detail) return error.detail
    if (error.status === 422) return 'Revisa el nombre y el tipo de reparto.'
  }
  return 'No se pudo guardar el servicio. Vuelve a intentarlo.'
}

function ServiceForm({ buildingId, onCreated }: { buildingId: string; onCreated: () => void }) {
  const onSessionEnded = useOutletContext<() => void>()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const name = String(data.get('name') ?? '').trim()
    const calculationType = data.get('calculation_type')
    if (name.length < 3 || (calculationType !== 'LINEAR' && calculationType !== 'METERED')) {
      setError('Ingresa al menos tres caracteres y elige el tipo de reparto.')
      return
    }

    setSaving(true)
    setError('')
    try {
      await createService(buildingId, { name, calculation_type: calculationType })
      onCreated()
    } catch (issue) {
      if (issue instanceof PropertyRequestError && issue.status === 401) onSessionEnded()
      else setError(saveError(issue))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="building-surface" aria-labelledby="service-form-title">
      <h2 id="service-form-title">Nuevo servicio</h2>
      <form className="building-form" onSubmit={submit} aria-busy={saving}>
        <div className="building-form-grid">
          <label>
            Nombre
            <input name="name" minLength={3} maxLength={50} required disabled={saving} />
          </label>
          <label>
            Tipo de reparto
            <select name="calculation_type" defaultValue="" required disabled={saving}>
              <option value="" disabled>Selecciona el reparto</option>
              <option value="LINEAR">{calculationLabels.LINEAR}</option>
              <option value="METERED">{calculationLabels.METERED}</option>
            </select>
          </label>
        </div>
        {error && <p role="alert" className="form-error">{error}</p>}
        <button type="submit" disabled={saving}>{saving ? 'Guardando…' : 'Crear servicio'}</button>
      </form>
    </section>
  )
}

function ServiceCatalog({ buildingId }: { buildingId: string }) {
  const load = useCallback(async (signal: AbortSignal) => {
    const [building, services] = await Promise.all([
      readBuilding(buildingId, signal),
      listServices(buildingId, signal),
    ])
    return { building, services }
  }, [buildingId])
  const { query, retry } = usePropertyQuery(load)

  return (
    <section className="building-page" aria-labelledby="service-catalog-title">
      <Link to={`/admin/edificios/${buildingId}`}>Volver al edificio</Link>
      <h1 id="service-catalog-title">Servicios</h1>
      {query.status === 'loading' && <p role="status">Cargando servicios…</p>}
      {query.status === 'error' && (
        query.error instanceof PropertyRequestError && query.error.status === 404
          ? <p role="alert">No se encontró el edificio.</p>
          : <div>
            <p role="alert">No se pudo cargar el catálogo.</p>
            <button type="button" onClick={retry}>Volver a intentar</button>
          </div>
      )}
      {query.status === 'ready' && (
        <>
          <p>{query.data.building.name}</p>
          <div className="building-grid">
            <ServiceForm buildingId={buildingId} onCreated={retry} />
            <section className="building-surface" aria-labelledby="service-list-title">
              <h2 id="service-list-title">Servicios registrados</h2>
              {query.data.services.length === 0 ? (
                <p>Todavía no hay servicios registrados.</p>
              ) : (
                <dl className="building-details">
                  {query.data.services.map((service) => (
                    <div key={service.id}>
                      <dt>{service.name}</dt>
                      <dd>{calculationLabels[service.calculation_type]}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </section>
          </div>
        </>
      )}
    </section>
  )
}

export function ServiceCatalogPage() {
  const { buildingId } = useParams()
  return buildingId
    ? <ServiceCatalog key={buildingId} buildingId={buildingId} />
    : <Navigate to="/admin" replace />
}
