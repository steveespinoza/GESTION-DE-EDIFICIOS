import { useCallback, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'

import { PropertyRequestError } from '../properties/api'
import { usePropertyQuery } from '../properties/usePropertyQuery'
import { readStatement, type Payment, type Period, type Statement } from './api'
import { PaymentForm } from './PaymentForm'
import { OwnerReports } from './OwnerReports'
import { ChargeAdjustmentHistory } from '../billing/ChargeAdjustmentHistory'
import { money, periodLabel } from './format'
import './collections.css'

const periodKey = (period: Period) => `${period.billing_year}-${String(period.billing_month).padStart(2, '0')}`

function StatementContent({ statement }: { statement: Statement }) {
  const [selected, setSelected] = useState('')
  const periods = new Map([...statement.charges, ...statement.payments, ...statement.carry_forwards].map((item) => [periodKey(item), item]))
  const charges = statement.charges.filter((charge) => !selected || periodKey(charge) === selected)
  const payments = statement.payments.filter((payment) => !selected || periodKey(payment) === selected || payment.applications.some((application) => periodKey(application) === selected))
  const carries = statement.carry_forwards.filter((carry) => !selected || periodKey(carry) === selected)
  const adjustments = statement.adjustments.filter((adjustment) => !selected || periodKey(adjustment) === selected)

  return (
    <>
      <section className="building-surface" aria-labelledby="statement-summary">
        <h2 id="statement-summary">{statement.building_name} · Unidad {statement.unit_number}</h2>
        <dl className="building-details">
          <div><dt>Pendiente de todos los periodos</dt><dd>{money(statement.balance)}</dd></div>
          <div><dt>Crédito de la unidad</dt><dd>{money(statement.credit)}</dd></div>
        </dl>
        <p>El crédito disponible se aplica automáticamente a los cargos pendientes más antiguos de esta unidad.</p>
      </section>
      {periods.size > 0 && (
        <div className="building-form statement-period">
          <label>Filtrar por periodo <select value={selected} onChange={(event) => setSelected(event.target.value)}>
            <option value="">Todos los periodos</option>
            {[...periods.entries()].sort(([left], [right]) => right.localeCompare(left)).map(([key, item]) => (
              <option key={key} value={key}>{periodLabel(item)}</option>
            ))}
          </select></label>
        </div>
      )}
      <div className="building-grid">
        <section className="building-surface" aria-labelledby="statement-charges">
          <h2 id="statement-charges">Cargos</h2>
          {charges.length === 0 ? <p>No hay cargos en el periodo seleccionado.</p> : (
            <dl className="building-details">
              {charges.map((charge) => (
                <div key={charge.id}>
                  <dt>{charge.service} · {periodLabel(charge)}</dt>
                  <dd>Importe {money(charge.amount)} · Pendiente {money(charge.balance)}</dd>
                  {charge.adjustment !== '0.00' && <dd>Original {money(charge.original_amount)} · Ajustes {money(charge.adjustment)}</dd>}
                  <dd>Aplicado {money(charge.applied)} · Cobertura hasta {charge.coverage_end}</dd>
                  {charge.consumption !== null && <dd>Consumo propio {charge.consumption.replace('.', ',')} m³</dd>}
                </div>
              ))}
            </dl>
          )}
        </section>
        <section className="building-surface" aria-labelledby="statement-payments">
          <h2 id="statement-payments">Pagos registrados</h2>
          {selected && <p>Incluye pagos del periodo y pagos anteriores aplicados a sus cargos.</p>}
          {payments.length === 0 ? <p>No hay pagos en el periodo seleccionado.</p> : (
            <div className="building-details">
              {payments.map((payment) => (
                <details key={payment.id}>
                  <summary>{payment.received_on} · {money(payment.amount)}</summary>
                  <p>Periodo de referencia {periodLabel(payment)}</p>
                  {payment.reference && <p>Referencia {payment.reference}</p>}
                  {payment.credit !== '0.00' && <p>Crédito disponible {money(payment.credit)}</p>}
                  {payment.applications.length > 0 && (
                    <ul>
                      {payment.applications.map((application) => (
                        <li key={application.id}>
                          {application.service} · {periodLabel(application)} · Aplicación vigente {money(application.net_amount)}
                          {application.released !== '0.00' && <> · Aplicado inicialmente {money(application.amount)} · Liberado por ajustes {money(application.released)}</>}
                          {application.automatic && ' · Crédito aplicado automáticamente'}
                          {' · '}{application.applied_by ?? 'Sistema'} · <time dateTime={application.applied_at}>{new Date(application.applied_at).toLocaleString('es-PE')}</time>
                        </li>
                      ))}
                    </ul>
                  )}
                </details>
              ))}
            </div>
          )}
        </section>
      </div>
      <section className="building-surface" aria-labelledby="statement-carry">
        <h2 id="statement-carry">Saldos de periodos anteriores</h2>
        <p>El total pendiente ya incluye estos saldos. Cada registro conserva el importe al arrastrarlo y el saldo actual del cargo de origen.</p>
        {carries.length === 0 ? <p>No hay arrastres en el periodo seleccionado.</p> : (
          <dl className="building-details">
            {carries.map((carry) => (
              <div key={`${carry.charge_id}:${periodKey(carry)}`}>
                <dt>{carry.service} · De {periodLabel({ billing_year: carry.source_year, billing_month: carry.source_month })} a {periodLabel(carry)}</dt>
                <dd>Saldo al arrastrar {money(carry.amount)} · Pendiente actual {money(carry.balance)}</dd>
                <dd>{carry.recorded_by ?? 'Sistema'} · <time dateTime={carry.recorded_at}>{new Date(carry.recorded_at).toLocaleString('es-PE')}</time></dd>
              </div>
            ))}
          </dl>
        )}
      </section>
      <ChargeAdjustmentHistory adjustments={adjustments} />
    </>
  )
}

function UnitStatement({ unitId, buildingId }: { unitId: string; buildingId?: string }) {
  const [saved, setSaved] = useState<Payment>()
  const load = useCallback((signal: AbortSignal) => readStatement(unitId, buildingId, signal), [unitId, buildingId])
  const { query, retry } = usePropertyQuery(load)
  const back = buildingId ? `/admin/edificios/${buildingId}/unidades/${unitId}` : `/propietario/unidades/${unitId}`

  function onSaved(payment: Payment) {
    setSaved(payment)
    retry()
  }

  return (
    <section className="building-page unit-statement" aria-labelledby="statement-title">
      <Link to={back}>Volver a la unidad</Link>
      <h1 id="statement-title">Estado de cuenta</h1>
      {saved && <p role="status">Pago de {money(saved.amount)} registrado.</p>}
      {query.status === 'loading' && <p role="status">Cargando estado de cuenta…</p>}
      {query.status === 'error' && (
        <div>
          <p role="alert">{query.error instanceof PropertyRequestError && query.error.status === 404 ? 'No se encontró la unidad.' : 'No se pudo cargar el estado de cuenta.'}</p>
          <button type="button" onClick={retry}>Volver a intentar</button>
        </div>
      )}
      {query.status === 'ready' && (
        <>
          <StatementContent statement={query.data} />
          {buildingId && <PaymentForm buildingId={buildingId} unitId={unitId} period={query.data.charges.at(-1)} onSaved={onSaved} />}
          {!buildingId && <OwnerReports unitId={unitId} period={query.data.charges.at(-1)} />}
        </>
      )}
    </section>
  )
}

export function StatementPage() {
  const { buildingId, unitId } = useParams()
  return unitId ? <UnitStatement key={`${buildingId}:${unitId}`} unitId={unitId} buildingId={buildingId} /> : <Navigate to="/" replace />
}
