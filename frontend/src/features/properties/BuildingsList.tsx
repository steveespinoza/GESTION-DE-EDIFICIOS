import { Link } from 'react-router-dom'

import { buildingErrorMessage, listBuildings } from './api'
import { usePropertyQuery } from './usePropertyQuery'
import { WorkspaceIcon } from './WorkspaceIcon'

export function BuildingsList() {
  const { query, retry } = usePropertyQuery(listBuildings)

  return (
    <section className="building-page" aria-labelledby="buildings-title">
      <div className="building-page-heading">
        <h1 id="buildings-title">Edificios</h1>
        <Link className="button-link" to="edificios/nuevo">Nuevo edificio</Link>
      </div>
      <p className="page-description">Selecciona un edificio para administrar sus unidades, servicios y cobranzas.</p>
      {query.status === 'loading' && <p role="status">Cargando edificios…</p>}
      {query.status === 'error' && (
        <div>
          <p role="alert">{buildingErrorMessage(query.error, 'No se pudo cargar el listado.')}</p>
          <button type="button" onClick={retry}>Volver a intentar</button>
        </div>
      )}
      {query.status === 'ready' && (query.data.length === 0 ? (
        <p className="building-surface">Todavía no hay edificios registrados.</p>
      ) : (
        <ul className="building-grid building-hub-grid">
          {query.data.map((building) => (
            <li key={building.id}>
              <Link className="building-hub-card" to={`edificios/${building.id}`} aria-label={building.name}>
                <span className="module-icon"><WorkspaceIcon name="building" /></span>
                <div className="module-copy"><h2>{building.name}</h2><p>{building.address ?? 'Sin dirección registrada'}</p><span className="capacity-badge">Capacidad: {building.total_units} {building.total_units === 1 ? 'unidad' : 'unidades'}</span></div>
                <WorkspaceIcon name="arrow" />
              </Link>
            </li>
          ))}
        </ul>
      ))}
    </section>
  )
}
