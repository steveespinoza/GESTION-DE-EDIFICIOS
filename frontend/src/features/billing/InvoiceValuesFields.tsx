import type { InvoiceValues } from './invoiceApi'

export function readInvoiceValues(fields: FormData): InvoiceValues {
  const text = (name: string) => String(fields.get(name) ?? '')
  const units = fields.getAll('meter_unit').map(String)
  return {
    start_date: text('start_date'),
    end_date: text('end_date'),
    total_amount: text('total_amount'),
    ...(units.length > 0 ? {
      total_volume: text('total_volume'),
      readings: units.map((unitId) => ({
        unit_id: unitId,
        previous_reading: text(`previous_${unitId}`),
        current_reading: text(`current_${unitId}`),
        rollover_confirmed: fields.has(`rollover_${unitId}`),
      })),
    } : {}),
  }
}

export function InvoiceValuesFields({ values }: { values?: InvoiceValues }) {
  return (
    <>
      <label>Fecha de inicio<input name="start_date" type="date" defaultValue={values?.start_date} required /></label>
      <label>Fecha de fin<input name="end_date" type="date" defaultValue={values?.end_date} required /></label>
      <label className="building-form-wide">
        Monto total (S/)
        <input name="total_amount" type="number" min="0.01" max="9999999999.99" step="0.01" inputMode="decimal" defaultValue={values?.total_amount} required />
      </label>
    </>
  )
}
