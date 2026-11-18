import { useRef, useState, type FormEvent } from 'react'
import { useOutletContext } from 'react-router-dom'

import { PropertyRequestError } from '../properties/api'
import { money } from '../collections/format'
import { adjustCharge, type InvoiceDetail } from './invoiceApi'

export function ChargeAdjustmentForm({ buildingId, invoice, onSaved, onReload, onStart }: { buildingId: string; invoice: InvoiceDetail; onSaved: () => void; onReload: () => void; onStart: () => void }) {
  const onSessionEnded = useOutletContext<() => void>()
  const [selected, setSelected] = useState(invoice.charges[0]?.id ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const requestId = useRef<string | null>(null)
  const charge = invoice.charges.find((item) => item.id === selected)
  if (!invoice.accounting_locked || !charge) return null

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (saving || !charge) return
    const fields = new FormData(event.currentTarget)
    requestId.current ??= crypto.randomUUID()
    onStart()
    setSaving(true)
    setError('')
    try {
      await adjustCharge(buildingId, invoice.id, charge.id, {
        request_id: requestId.current,
        revision: charge.adjustment_revision,
        new_amount: String(fields.get('new_amount')),
        reason: String(fields.get('reason')).trim(),
      })
      onSaved()
    } catch (issue) {
      if (issue instanceof PropertyRequestError && issue.status === 401) onSessionEnded()
      else if (issue instanceof PropertyRequestError && issue.detail) setError(issue.detail)
      else if (issue instanceof PropertyRequestError && issue.status === 422) setError('Revisa el nuevo importe y el motivo.')
      else setError('No se pudo confirmar el ajuste. Revisa el historial antes de reintentar con los mismos datos.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="building-surface" aria-labelledby="new-charge-adjustment-title">
      <h2 id="new-charge-adjustment-title">Ajustar un cargo</h2>
      <p>La factura y el cargo original conservan sus importes. El ajuste registra la diferencia y su motivo. Si libera dinero pagado, el crédito se aplica automáticamente a los otros cargos pendientes de la unidad.</p>
      <form className="building-form" onSubmit={submit} aria-busy={saving}>
        <fieldset className="building-form-grid" disabled={saving}>
          <legend>Importe vigente y corrección</legend>
          <label>Unidad<select value={selected} onChange={(event) => { setSelected(event.target.value); requestId.current = null; setError('') }}>
            {invoice.charges.map((item) => <option key={item.id} value={item.id}>Unidad {item.unit_number} · {money(item.adjusted_amount)}</option>)}
          </select></label>
          <label>Nuevo importe del cargo (S/)<input key={selected} name="new_amount" type="number" min="0" max="9999999999.99" step="0.01" inputMode="decimal" defaultValue={charge.adjusted_amount} required /></label>
          <label className="building-form-wide">Motivo del ajuste<textarea name="reason" maxLength={500} rows={3} required /></label>
        </fieldset>
        {error && <p role="alert" className="form-error">{error}</p>}
        {error && <button type="button" disabled={saving} onClick={onReload}>Actualizar factura e historial</button>}
        <button type="submit" disabled={saving}>{saving ? 'Registrando ajuste…' : 'Registrar ajuste'}</button>
      </form>
    </section>
  )
}
