import { useState, type FormEvent } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'

import { PropertyRequestError } from '../properties/api'
import type { ServiceCategory } from './api'
import { createInvoice, invoicePath } from './invoiceApi'
import { MeterFields } from './MeterFields'

const monthFormatter = new Intl.DateTimeFormat('es-PE', { month: 'long', timeZone: 'UTC' })
export const billingMonths = Array.from({ length: 12 }, (_, index) => ({
  number: index + 1,
  name: monthFormatter.format(new Date(Date.UTC(2020, index, 1))).toLocaleLowerCase('es-PE'),
}))

function submissionError(error: unknown) {
  if (error instanceof PropertyRequestError) {
    if (error.status === 409 && error.detail) return error.detail
    if (error.status === 422) return 'Revisa el periodo, las fechas y el importe de la factura.'
    if (error.status === 404) return 'El servicio seleccionado ya no está disponible.'
  }
  return 'No se pudo confirmar el registro. Revisa el historial antes de volver a intentarlo.'
}

export function InvoiceForm({ buildingId, categories }: { buildingId: string; categories: ServiceCategory[] }) {
  const navigate = useNavigate()
  const onSessionEnded = useOutletContext<() => void>()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [month, setMonth] = useState('')
  const [year, setYear] = useState('')
  const metered = categories.find((category) => category.id === categoryId)?.calculation_type === 'METERED'
  const periodReady = Boolean(month) && /^[2-9]\d{3}$/.test(year) && Number(year) >= 2020

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const fields = new FormData(event.currentTarget)
    const text = (name: string) => String(fields.get(name) ?? '')
    const start = text('start_date')
    const end = text('end_date')
    if (end < start) {
      setError('La fecha de fin debe ser igual o posterior a la de inicio.')
      return
    }
    const meterUnits = fields.getAll('meter_unit').map(String)
    if (metered && meterUnits.length === 0) {
      setError('Carga las lecturas del periodo antes de registrar la factura.')
      return
    }
    setSaving(true)
    setError('')
    try {
      const invoice = await createInvoice(buildingId, {
        category_id: text('category_id'),
        billing_year: Number(text('billing_year')),
        billing_month: Number(text('billing_month')),
        start_date: start,
        end_date: end,
        total_amount: text('total_amount'),
        ...(metered ? {
          total_volume: text('total_volume'),
          readings: meterUnits.map((unitId) => ({
            unit_id: unitId,
            previous_reading: text(`previous_${unitId}`),
            current_reading: text(`current_${unitId}`),
            rollover_confirmed: fields.has(`rollover_${unitId}`),
          })),
        } : {}),
      })
      void navigate(`${invoicePath(buildingId)}/${invoice.id}`)
    } catch (issue) {
      if (issue instanceof PropertyRequestError && issue.status === 401) onSessionEnded()
      else setError(submissionError(issue))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="building-form" onSubmit={submit} aria-busy={saving}>
      <fieldset disabled={saving}>
        <div className="building-form-grid">
          <div className="building-form-wide invoice-service-field">
            <label htmlFor="invoice-service">Servicio</label>
            <select id="invoice-service" name="category_id" value={categoryId} onChange={(event) => setCategoryId(event.target.value)} required>
              <option value="" disabled>Selecciona un servicio</option>
              {categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
            </select>
          </div>
          <label>
            Mes contable
            <select name="billing_month" value={month} onChange={(event) => setMonth(event.target.value)} required>
              <option value="" disabled>Selecciona el mes</option>
              {billingMonths.map((month) => <option key={month.number} value={month.number}>{month.name}</option>)}
            </select>
          </label>
          <label>Año contable<input name="billing_year" type="number" min={2020} max={9999} step={1} value={year} onChange={(event) => setYear(event.target.value)} required /></label>
          <label>Fecha de inicio<input name="start_date" type="date" required /></label>
          <label>Fecha de fin<input name="end_date" type="date" required /></label>
          <label className="building-form-wide">
            Monto total (S/)
            <input name="total_amount" type="number" min="0.01" max="9999999999.99" step="0.01" inputMode="decimal" required />
          </label>
        </div>
      </fieldset>
      {metered && (
        <fieldset disabled={saving}>
          <legend>Lecturas del contador</legend>
          {periodReady ? (
            <MeterFields key={`${categoryId}:${year}:${month}`} buildingId={buildingId} categoryId={categoryId} year={year} month={month} />
          ) : <p>Selecciona el mes y el año contable para cargar las lecturas.</p>}
        </fieldset>
      )}
      {error && <p role="alert" className="form-error">{error}</p>}
      <button type="submit" disabled={saving}>{saving ? 'Registrando…' : 'Registrar factura'}</button>
    </form>
  )
}
