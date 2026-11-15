import { useCallback } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'

import { PropertyRequestError, readBuilding } from '../properties/api'
import { usePropertyQuery } from '../properties/usePropertyQuery'
import { listServices } from './api'
import { billingMonths, InvoiceForm } from './InvoiceForm'
import { invoicePath, listInvoices, readInvoice } from './invoiceApi'

const money = (amount: string) => `S/ ${amount.replace('.', ',')}`
const volume = (amount: string) => `${amount.replace('.', ',')} m³`
const period = (month: number, year: number) => `${billingMonths[month - 1].name} de ${year}`

function LoadError({ error, retry }: { error: unknown; retry: () => void }) {
  if (error instanceof PropertyRequestError && error.status === 404) {
    return <p role="alert">No se encontró el edificio o la factura.</p>
  }
  return (
    <div>
      <p role="alert">No se pudo cargar la facturación.</p>
      <button type="button" onClick={retry}>Volver a intentar</button>
    </div>
  )
}

function InvoiceHistory({ buildingId }: { buildingId: string }) {
  const load = useCallback(async (signal: AbortSignal) => {
    const [building, services, invoices] = await Promise.all([
      readBuilding(buildingId, signal),
      listServices(buildingId, signal),
      listInvoices(buildingId, signal),
    ])
    return { building, services, invoices }
  }, [buildingId])
  const { query, retry } = usePropertyQuery(load)

  return (
    <section className="building-page" aria-labelledby="invoice-history-title">
      <Link to={`/admin/edificios/${buildingId}`}>Volver al edificio</Link>
      <h1 id="invoice-history-title">Facturas</h1>
      {query.status === 'loading' && <p role="status">Cargando facturas…</p>}
      {query.status === 'error' && <LoadError error={query.error} retry={retry} />}
      {query.status === 'ready' && (
        <>
          <p>{query.data.building.name}</p>
          <div className="building-grid">
            <section className="building-surface" aria-labelledby="new-invoice-title">
              <h2 id="new-invoice-title">Nueva factura</h2>
              {query.data.services.length > 0 ? (
                <InvoiceForm buildingId={buildingId} categories={query.data.services} />
              ) : (
                <p><Link to={`/admin/edificios/${buildingId}/servicios`}>Registra un servicio</Link> para facturarlo.</p>
              )}
            </section>
            <section className="building-surface" aria-labelledby="history-title">
              <h2 id="history-title">Historial</h2>
              {query.data.invoices.length === 0 ? <p>Todavía no hay facturas registradas.</p> : (
                <dl className="building-details">
                  {query.data.invoices.map((invoice) => (
                    <div key={invoice.id}>
                      <dt><Link to={`${invoicePath(buildingId)}/${invoice.id}`}>{invoice.category_name} · {period(invoice.billing_month, invoice.billing_year)}</Link></dt>
                      <dd>{money(invoice.total_amount)}</dd>
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

function InvoiceRecord({ buildingId, invoiceId }: { buildingId: string; invoiceId: string }) {
  const load = useCallback((signal: AbortSignal) => readInvoice(buildingId, invoiceId, signal), [buildingId, invoiceId])
  const { query, retry } = usePropertyQuery(load)

  return (
    <section className="building-page" aria-labelledby="invoice-title">
      <Link to={invoicePath(buildingId)}>Volver a facturas</Link>
      <h1 id="invoice-title">Detalle de factura</h1>
      {query.status === 'loading' && <p role="status">Cargando factura…</p>}
      {query.status === 'error' && <LoadError error={query.error} retry={retry} />}
      {query.status === 'ready' && (
        <div className="building-grid">
          <section className="building-surface" aria-labelledby="invoice-service-title">
            <h2 id="invoice-service-title">{query.data.category_name}</h2>
            <dl className="building-details">
              <div><dt>Periodo contable</dt><dd>{period(query.data.billing_month, query.data.billing_year)}</dd></div>
              <div><dt>Fecha de inicio</dt><dd>{query.data.start_date}</dd></div>
              <div><dt>Fecha de fin</dt><dd>{query.data.end_date}</dd></div>
              <div><dt>Monto total</dt><dd>{money(query.data.total_amount)}</dd></div>
              {query.data.total_volume !== undefined && (
                <div><dt>Volumen de la factura</dt><dd>{volume(query.data.total_volume)}</dd></div>
              )}
              {query.data.common_volume !== undefined && (
                <div><dt>Consumo común</dt><dd>{volume(query.data.common_volume)}</dd></div>
              )}
            </dl>
          </section>
          <section className="building-surface" aria-labelledby="charges-title">
            <h2 id="charges-title">Cargos por unidad</h2>
            <dl className="building-details">
              {query.data.charges.map((charge) => (
                <div key={charge.unit_id}>
                  <dt>Unidad {charge.unit_number}</dt>
                  <dd>{money(charge.amount)}</dd>
                  {charge.meter && (
                    <>
                      <dd>{volume(charge.meter.previous_reading)} → {volume(charge.meter.current_reading)}{charge.meter.rolled_over && ' · vuelta a cero'}</dd>
                      <dd>Consumo propio de {volume(charge.meter.consumption)} · {money(charge.meter.own_amount)}</dd>
                      <dd>Consumo común · {money(charge.meter.common_amount)}</dd>
                    </>
                  )}
                </div>
              ))}
            </dl>
          </section>
        </div>
      )}
    </section>
  )
}

export function InvoicePage() {
  const { buildingId, invoiceId } = useParams()
  if (!buildingId) return <Navigate to="/admin" replace />
  return invoiceId
    ? <InvoiceRecord key={`${buildingId}:${invoiceId}`} buildingId={buildingId} invoiceId={invoiceId} />
    : <InvoiceHistory key={buildingId} buildingId={buildingId} />
}
