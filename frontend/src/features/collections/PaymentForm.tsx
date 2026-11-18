import { useRef, useState, type FormEvent } from 'react'
import { useOutletContext } from 'react-router-dom'

import { PropertyRequestError } from '../properties/api'
import { registerPayment, type Payment, type Period } from './api'
import { PaymentFields, PaymentPeriodFields, readPaymentPeriod, readPaymentValues } from './PaymentFields'

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
        ...readPaymentPeriod(fields),
        ...readPaymentValues(fields),
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
          <legend>Periodo de referencia del pago</legend>
          <PaymentPeriodFields period={period} />
          <PaymentFields />
        </fieldset>
        <p>Se aplicará primero a los cargos pendientes más antiguos de esta unidad. El excedente cubrirá automáticamente nuevos cargos.</p>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button type="submit" disabled={saving}>{saving ? 'Registrando…' : 'Registrar pago'}</button>
      </form>
    </section>
  )
}
