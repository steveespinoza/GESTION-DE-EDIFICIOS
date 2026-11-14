import { useCallback, type FormEvent } from 'react'
import { Link, Navigate, useParams, useSearchParams } from 'react-router-dom'

import { UnitEditor } from './UnitEditor'
import { listOwners, listUnits, readUnit, unitErrorMessage, unitsPath } from './unitsApi'
import { usePropertyQuery } from './usePropertyQuery'

function LoadError({ error, retry }: { error: unknown; retry: () => void }) {
  return (
    <div>
      <p role="alert">{unitErrorMessage(error, 'No se pudo cargar la información.')}</p>
      <button type="button" onClick={retry}>Volver a intentar</button>
    </div>
  )
}

function UnitResults({ buildingId, filter }: { buildingId: string; filter: string }) {
  const load = useCallback((signal: AbortSignal) => listUnits(buildingId, filter, signal), [buildingId, filter])
  const { query, retry } = usePropertyQuery(load)
  if (query.status === 'loading') return <p role="status">Cargando unidades…</p>
  if (query.status === 'error') return <LoadError error={query.error} retry={retry} />
  if (query.data.length === 0) {
    return <p className="building-surface">{filter ? 'No hay unidades que coincidan con la búsqueda.' : 'Todavía no hay unidades registradas.'}</p>
  }

  return (
    <ul className="building-grid">
      {query.data.map((unit) => (
        <li key={unit.id} className="building-surface">
          <h2><Link to={`${unitsPath(buildingId)}/${unit.id}`}>Unidad {unit.number}</Link></h2>
          <p>{unit.owner.full_name}</p>
          <p>{unit.area_sqm} m²</p>
        </li>
      ))}
    </ul>
  )
}

export function UnitsList() {
  const { buildingId } = useParams()
  const [search, setSearch] = useSearchParams()
  const filter = search.get('q') ?? ''
  if (!buildingId) return <Navigate to="/admin" replace />

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const term = String(new FormData(event.currentTarget).get('q') ?? '').trim()
    setSearch(term ? { q: term } : {})
  }

  return (
    <section className="building-page" aria-labelledby="units-title">
      <Link to={`/admin/edificios/${buildingId}`}>Volver al edificio</Link>
      <div className="building-page-heading">
        <h1 id="units-title">Unidades</h1>
        <Link className="button-link" to="nueva">Nueva unidad</Link>
      </div>
      <form key={filter} className="unit-search" role="search" onSubmit={submitSearch}>
        <label>
          Número o propietario
          <input name="q" type="search" defaultValue={filter} maxLength={150} />
        </label>
        <button type="submit">Buscar</button>
        {filter && <Link to={unitsPath(buildingId)}>Limpiar búsqueda</Link>}
      </form>
      <UnitResults key={`${buildingId}:${filter}`} buildingId={buildingId} filter={filter} />
    </section>
  )
}

function NewUnit({ buildingId }: { buildingId: string }) {
  const { query, retry } = usePropertyQuery(listOwners)
  if (query.status === 'loading') return <p role="status">Cargando propietarios…</p>
  if (query.status === 'error') return <LoadError error={query.error} retry={retry} />
  return <UnitEditor buildingId={buildingId} owners={query.data} />
}

export function NewUnitPage() {
  const { buildingId } = useParams()
  return buildingId ? <NewUnit key={buildingId} buildingId={buildingId} /> : <Navigate to="/admin" replace />
}

function UnitRecord({ buildingId, unitId, mode }: { buildingId: string; unitId: string; mode: UnitMode }) {
  const load = useCallback((signal: AbortSignal) => readUnit(buildingId, unitId, signal), [buildingId, unitId])
  const { query, retry } = usePropertyQuery(load)
  if (query.status === 'loading') return <p role="status">Cargando unidad…</p>
  if (query.status === 'error') return <LoadError error={query.error} retry={retry} />

  const unit = query.data
  if (mode !== 'detail') return <UnitEditor buildingId={buildingId} unit={unit} editOwner={mode === 'owner'} />

  return (
    <section className="building-page" aria-labelledby="unit-title">
      <Link to={unitsPath(buildingId)}>Volver a unidades</Link>
      <div className="building-page-heading">
        <h1 id="unit-title">Unidad {unit.number}</h1>
        <Link className="button-link" to="editar">Editar unidad</Link>
      </div>
      <div className="building-grid">
        <section className="building-surface">
          <h2>Datos de la unidad</h2>
          <dl className="building-details">
            <div><dt>Área</dt><dd>{unit.area_sqm} m²</dd></div>
          </dl>
        </section>
        <section className="building-surface">
          <div className="building-page-heading">
            <h2>Propietario</h2>
            <Link to="propietario">Editar propietario</Link>
          </div>
          <dl className="building-details">
            <div><dt>Nombre completo</dt><dd>{unit.owner.full_name}</dd></div>
            <div><dt>Usuario</dt><dd>{unit.owner.username}</dd></div>
            <div><dt>Correo</dt><dd>{unit.owner.email ?? '—'}</dd></div>
            <div><dt>Teléfono</dt><dd>{unit.owner.phone ?? '—'}</dd></div>
          </dl>
        </section>
      </div>
    </section>
  )
}

type UnitMode = 'detail' | 'unit' | 'owner'

export function UnitPage({ mode = 'detail' }: { mode?: UnitMode }) {
  const { buildingId, unitId } = useParams()
  return buildingId && unitId
    ? <UnitRecord key={`${buildingId}:${unitId}`} buildingId={buildingId} unitId={unitId} mode={mode} />
    : <Navigate to="/admin" replace />
}
