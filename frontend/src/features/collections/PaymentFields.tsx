import type { PaymentValues, Period } from './api'

export function readPaymentValues(fields: FormData): PaymentValues {
  return {
    received_on: String(fields.get('received_on')),
    amount: String(fields.get('amount')),
    reference: String(fields.get('reference')).trim() || null,
  }
}

export function readPaymentPeriod(fields: FormData): Period {
  return {
    billing_year: Number(fields.get('billing_year')),
    billing_month: Number(fields.get('billing_month')),
  }
}

export function PaymentPeriodFields({ period }: { period?: Period }) {
  return (
    <>
      <label>Mes contable<input type="number" name="billing_month" min={1} max={12} step={1} defaultValue={period?.billing_month} required /></label>
      <label>Año contable<input type="number" name="billing_year" min={2020} max={9999} step={1} defaultValue={period?.billing_year} required /></label>
    </>
  )
}

export function PaymentFields({ values, reported }: { values?: PaymentValues; reported?: boolean }) {
  return (
    <>
      <label>{reported ? 'Fecha del pago' : 'Fecha de recepción'}<input type="date" name="received_on" defaultValue={values?.received_on} required /></label>
      <label>{reported ? 'Monto pagado (S/)' : 'Monto recibido (S/)'}<input type="number" name="amount" min="0.01" max="9999999999.99" step="0.01" inputMode="decimal" defaultValue={values?.amount} required /></label>
      <label className="building-form-wide">Referencia (opcional)<input name="reference" defaultValue={values?.reference ?? ''} maxLength={120} /></label>
    </>
  )
}
