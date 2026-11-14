import { Link } from 'react-router-dom'

import { buildingErrorMessage, listBuildings } from './api'
import { useBuildingQuery } from './useBuildingQuery'

export function BuildingsList() {
  const { query, retry } = useBuildingQuery(listBuildings)

  return (
    <section className="building-page" aria-labelledby="buildings-title">
      <div className="building-page-heading">
        <h1 id="buildings-title">Edificios</h1>
        <Link className="button-link" to="edificios/nuevo">Nuevo edificio</Link>
      </div>
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
        <ul className="building-grid">
          {query.data.map((building) => (
            <li className="building-surface" key={building.id}>
              <h2><Link to={`edificios/${building.id}`}>{building.name}</Link></h2>
              {building.address && <p>{building.address}</p>}
              <p>Capacidad de {building.total_units} unidades</p>
            </li>
          ))}
        </ul>
      ))}
    </section>
  )
}
