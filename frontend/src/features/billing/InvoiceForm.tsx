import { useState, type FormEvent } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'

import { PropertyRequestError } from '../properties/api'
import type { ServiceCategory } from './api'
import { createInvoice, invoicePath } from './invoiceApi'

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
          <label className="building-form-wide">
            Servicio lineal
            <select name="category_id" defaultValue="" required>
              <option value="" disabled>Selecciona un servicio</option>
              {categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
            </select>
          </label>
          <label>
            Mes contable
            <select name="billing_month" defaultValue="" required>
              <option value="" disabled>Selecciona el mes</option>
              {billingMonths.map((month) => <option key={month.number} value={month.number}>{month.name}</option>)}
            </select>
          </label>
          <label>Año contable<input name="billing_year" type="number" min={2020} max={9999} step={1} required /></label>
          <label>Fecha de inicio<input name="start_date" type="date" required /></label>
          <label>Fecha de fin<input name="end_date" type="date" required /></label>
          <label className="building-form-wide">
            Monto total (S/)
            <input name="total_amount" type="number" min="0.01" max="9999999999.99" step="0.01" inputMode="decimal" required />
          </label>
        </div>
      </fieldset>
      {error && <p role="alert" className="form-error">{error}</p>}
      <button type="submit" disabled={saving}>{saving ? 'Registrando…' : 'Registrar factura'}</button>
    </form>
  )
}
