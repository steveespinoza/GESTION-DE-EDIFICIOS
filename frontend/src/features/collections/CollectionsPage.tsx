import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'

import { PropertyRequestError } from '../properties/api'
import { usePropertyQuery } from '../properties/usePropertyQuery'
import type { Period } from './api'
import { readCollections, type CollectionOverview, type Deadline } from './deadlineApi'
import { DeadlineForm } from './DeadlineForm'
import { ConsolidationPanel } from './ConsolidationPanel'
import { MonthlyExcelPanel } from './MonthlyExcelPanel'
import { money, periodLabel } from './format'
import './collections.css'

const periodKey = (period: Period) => `${period.billing_year}-${String(period.billing_month).padStart(2, '0')}`

function CollectionsContent({ buildingId, data, onSaved, refresh, saved }: { buildingId: string; data: CollectionOverview; onSaved: (deadline: Deadline) => void; refresh: () => void; saved?: Deadline }) {
  const [selected, setSelected] = useState('')
  const [overdueOnly, setOverdueOnly] = useState(false)
  const periods = [...new Map([...data.rows, ...data.deadlines].map((row) => [periodKey(row), row])).entries()].sort(([a], [b]) => b.localeCompare(a))
  const [deadlinePeriod, setDeadlinePeriod] = useState(saved ? periodKey(saved) : periods[0]?.[0] ?? '')
  const period = periods.find(([key]) => key === deadlinePeriod)?.[1]
  const current = data.deadlines.find((item) => periodKey(item) === deadlinePeriod)
  const rows = data.rows.filter((row) => (!selected || periodKey(row) === selected) && (!overdueOnly || row.overdue_balance !== '0.00'))

  return (
    <>
      <section className="building-surface" aria-labelledby="collections-summary">
        <h2 id="collections-summary">{data.building_name}</h2>
        <dl className="building-details">
          <div><dt>Pendiente de todos los periodos</dt><dd>{money(data.balance)}</dd></div>
          <div><dt>De ese pendiente, vencido</dt><dd>{money(data.overdue_balance)}</dd></div>
        </dl>
        <p>Vencimientos al {data.as_of} (hora de Lima). El importe pasa a vencido al día siguiente de la fecha límite.</p>
        <p>Los arrastres conservan la fecha del cargo de origen. Los periodos sin fecha se muestran como «Sin vencimiento».</p>
      </section>
      <ConsolidationPanel buildingId={buildingId} periods={data.rows} />
      <MonthlyExcelPanel buildingId={buildingId} periods={data.rows} />
      <div className="building-form collections-filters">
        <label>Filtrar por periodo<select value={selected} onChange={(event) => setSelected(event.target.value)}>
          <option value="">Todos los periodos</option>
          {periods.map(([key, item]) => <option key={key} value={key}>{periodLabel(item)}</option>)}
        </select></label>
        <label className="collections-checkbox"><input type="checkbox" checked={overdueOnly} onChange={(event) => setOverdueOnly(event.target.checked)} />Solo deudas vencidas</label>
      </div>
      <section aria-labelledby="collections-list-title">
        <h2 id="collections-list-title">Cobranzas por unidad y periodo</h2>
        {rows.length === 0 ? <p role="status">No hay cobranzas con los filtros seleccionados.</p> : (
          <ul className="building-grid">
            {rows.map((row) => (
              <li className="building-surface" key={`${row.unit_id}:${periodKey(row)}`}>
                <h3>Unidad {row.unit_number} · {periodLabel(row)}</h3>
                <dl className="building-details">
                  <div><dt>Propietario</dt><dd>{row.owner_name}</dd></div>
                  <div><dt>Importe vigente</dt><dd>{money(row.amount)}</dd></div>
                  <div><dt>Aplicado</dt><dd>{money(row.applied)}</dd></div>
                  <div><dt>Pendiente</dt><dd>{money(row.balance)}</dd></div>
                  <div><dt>Vencido</dt><dd>{money(row.overdue_balance)}</dd></div>
                  <div><dt>Fecha límite</dt><dd>{row.due_date ?? 'Sin vencimiento'}</dd></div>
                  <div><dt>Estado</dt><dd>{row.balance === '0.00' ? 'Pagado' : row.overdue_balance !== '0.00' ? 'Vencido' : row.due_date ? 'Por vencer' : 'Sin vencimiento'}</dd></div>
                </dl>
                <p><Link to={`/admin/edificios/${buildingId}/unidades/${row.unit_id}/estado-de-cuenta`} aria-label={`Estado de cuenta de la unidad ${row.unit_number}, ${periodLabel(row)}`}>Estado de cuenta y pagos</Link></p>
              </li>
            ))}
          </ul>
        )}
      </section>
      {period && (
        <section className="building-surface" aria-labelledby="deadline-title">
          <h2 id="deadline-title">Registrar vencimiento</h2>
          <label className="building-form">Periodo del vencimiento<select value={deadlinePeriod} onChange={(event) => setDeadlinePeriod(event.target.value)}>
            {periods.map(([key, item]) => <option key={key} value={key}>{periodLabel(item)}</option>)}
          </select></label>
          <DeadlineForm key={`${deadlinePeriod}:${current?.revision ?? 0}`} buildingId={buildingId} period={{billing_year:period.billing_year,billing_month:period.billing_month}} current={current} onSaved={onSaved} refresh={refresh} />
          <details>
            <summary>Historial de vencimientos del periodo</summary>
            {data.deadlines.filter((item) => periodKey(item) === deadlinePeriod).map((item) => (
              <p key={item.id}>Revisión {item.revision} · {item.due_date} · {item.reason} · {item.recorded_by} · <time dateTime={item.recorded_at}>{new Date(item.recorded_at).toLocaleString('es-PE')}</time></p>
            ))}
            {!current && <p>Todavía no se registró una fecha.</p>}
          </details>
        </section>
      )}
    </>
  )
}

function CollectionsRecord({ buildingId }: { buildingId: string }) {
  const load = useCallback((signal: AbortSignal) => readCollections(buildingId, signal), [buildingId])
  const { query, retry } = usePropertyQuery(load)
  const [saved, setSaved] = useState<Deadline>()
  const notice = useRef<HTMLParagraphElement>(null)
  useEffect(() => { if (saved && query.status === 'ready') notice.current?.focus() }, [saved, query.status])

  return (
    <section className="building-page unit-statement" aria-labelledby="collections-title">
      <Link to={`/admin/edificios/${buildingId}`}>Volver al edificio</Link>
      <h1 id="collections-title">Cobranzas</h1>
      <Link className="button-link" to={`/admin/edificios/${buildingId}/recibos-por-lote`}>Emitir recibos por lote</Link>
      {saved && <p ref={notice} tabIndex={-1} role="status">Vencimiento de {periodLabel(saved)} registrado para {saved.due_date}.</p>}
      {query.status === 'loading' && <p role="status">Cargando cobranzas…</p>}
      {query.status === 'error' && <div><p role="alert">{query.error instanceof PropertyRequestError && query.error.status === 404 ? 'No se encontró el edificio.' : 'No se pudieron cargar las cobranzas.'}</p><button type="button" onClick={retry}>Volver a intentar</button></div>}
      {query.status === 'ready' && <CollectionsContent buildingId={buildingId} data={query.data} saved={saved} refresh={retry} onSaved={(item) => { setSaved(item); retry() }} />}
    </section>
  )
}

export function CollectionsPage() {
  const { buildingId } = useParams()
  return buildingId ? <CollectionsRecord key={buildingId} buildingId={buildingId} /> : <Navigate to="/admin" replace />
}
