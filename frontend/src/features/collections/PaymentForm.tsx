import { useRef, useState, type FormEvent } from 'react'
import { useOutletContext } from 'react-router-dom'

import { PropertyRequestError } from '../properties/api'
import { registerPayment, type Payment, type Period } from './api'

interface Props {
  buildingId: string
  unitId: string
  period?: Period
  onSaved: (payment: Payment) => void
}

export function PaymentForm({ buildingId, unitId, period, onSaved }: Props) {
  const onSessionEnded = useOutletContext<() => void>()
  const requestId = useRef<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (saving) return
    const fields = new FormData(event.currentTarget)
    requestId.current ??= crypto.randomUUID()
    setSaving(true)
    setError('')
    try {
      const payment = await registerPayment(buildingId, unitId, {
        request_id: requestId.current,
        billing_year: Number(fields.get('billing_year')),
        billing_month: Number(fields.get('billing_month')),
        received_on: String(fields.get('received_on')),
        amount: String(fields.get('amount')),
        reference: String(fields.get('reference')).trim() || null,
      })
      onSaved(payment)
    } catch (issue) {
      if (issue instanceof PropertyRequestError && issue.status === 401) onSessionEnded()
      else if (issue instanceof PropertyRequestError && issue.status === 409 && issue.detail) setError(issue.detail)
      else if (issue instanceof PropertyRequestError && issue.status === 422) setError('Revisa el importe, la fecha y el periodo.')
      else setError('No se pudo confirmar el registro. Reintenta con los mismos datos o revisa el historial antes de iniciar otro pago.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="building-surface" aria-labelledby="register-payment-title">
      <h2 id="register-payment-title">Registrar pago recibido</h2>
      <form className="building-form" onSubmit={submit} aria-busy={saving}>
        <fieldset className="building-form-grid" disabled={saving}>
          <legend>Aplicar a cargos hasta</legend>
          <label>Mes contable<input type="number" name="billing_month" min={1} max={12} step={1} defaultValue={period?.billing_month} required /></label>
          <label>Año contable<input type="number" name="billing_year" min={2020} max={9999} step={1} defaultValue={period?.billing_year} required /></label>
          <label>Fecha de recepción<input type="date" name="received_on" required /></label>
          <label>Monto recibido (S/)<input type="number" name="amount" min="0.01" max="9999999999.99" step="0.01" inputMode="decimal" required /></label>
          <label className="building-form-wide">Referencia (opcional)<input name="reference" maxLength={120} /></label>
        </fieldset>
        <p>Se aplicará primero a los cargos más antiguos. El excedente se registra como crédito.</p>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button type="submit" disabled={saving}>{saving ? 'Registrando…' : 'Registrar pago'}</button>
      </form>
    </section>
  )
}
