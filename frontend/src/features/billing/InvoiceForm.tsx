import { useState, type FormEvent } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'

import { PropertyRequestError } from '../properties/api'
import type { ServiceCategory } from './api'
import { createInvoice, invoicePath } from './invoiceApi'
import { InvoiceValuesFields, readInvoiceValues } from './InvoiceValuesFields'
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
    const values = readInvoiceValues(fields)
    if (values.end_date < values.start_date) {
      setError('La fecha de fin debe ser igual o posterior a la de inicio.')
      return
    }
    if (metered && !values.readings) {
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
        ...values,
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
          <InvoiceValuesFields />
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
