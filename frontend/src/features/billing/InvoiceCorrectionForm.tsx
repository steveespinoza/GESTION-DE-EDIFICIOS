import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useOutletContext } from 'react-router-dom'

import { PropertyRequestError } from '../properties/api'
import { correctInvoice, type InvoiceDetail } from './invoiceApi'
import { InvoiceValuesFields, readInvoiceValues } from './InvoiceValuesFields'
import { ReadingFields, VolumeField } from './MeterFields'

interface CorrectionProps {
  buildingId: string
  invoice: InvoiceDetail
  onSaved: (invoice: InvoiceDetail) => void
  onReload: () => void
}

export function InvoiceCorrectionForm({ buildingId, invoice, onSaved, onReload }: CorrectionProps) {
  const onSessionEnded = useOutletContext<() => void>()
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const heading = useRef<HTMLHeadingElement>(null)
  const start = useRef<HTMLButtonElement>(null)
  const restoreFocus = useRef(false)
  const volume = invoice.total_volume

  useEffect(() => {
    if (editing) heading.current?.focus()
    else if (restoreFocus.current) {
      start.current?.focus()
      restoreFocus.current = false
    }
  }, [editing])

  function close() {
    restoreFocus.current = true
    setEditing(false)
    setError('')
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const fields = new FormData(event.currentTarget)
    const values = readInvoiceValues(fields)
    const reason = String(fields.get('reason') ?? '').trim()
    if (values.end_date < values.start_date || !reason) {
      setError('Revisa el orden de las fechas e indica el motivo de la corrección.')
      return
    }
    setSaving(true)
    setError('')
    try {
      const updated = await correctInvoice(buildingId, invoice.id, { ...values, revision: invoice.revision, reason })
      setNotice(updated.revision === invoice.revision ? 'La factura conserva sus valores.' : 'Corrección guardada.')
      onSaved(updated)
      close()
    } catch (issue) {
      if (issue instanceof PropertyRequestError && issue.status === 401) {
        onSessionEnded()
      } else if (issue instanceof PropertyRequestError && issue.status === 409 && issue.detail) {
        setError(issue.detail)
      } else {
        setError('No se pudo confirmar la corrección. Revisa los valores o recarga la ficha para comprobar el estado.')
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="building-surface invoice-corrections" aria-labelledby="correction-title">
      <h2 id="correction-title">Correcciones</h2>
      {notice && <p role="status">{notice}</p>}
      {invoice.accounting_locked && <p>La factura tiene movimientos contables. La diferencia requiere un ajuste.</p>}
      {!editing && !invoice.accounting_locked && (
        <button ref={start} type="button" onClick={() => { setNotice(''); setEditing(true) }}>Corregir factura</button>
      )}
      {editing && (
        <form className="building-form" onSubmit={submit} aria-busy={saving} aria-labelledby="correction-form-title">
          <h3 id="correction-form-title" ref={heading} tabIndex={-1}>Corregir factura</h3>
          <fieldset disabled={saving} className="building-form-grid">
            <InvoiceValuesFields values={invoice} />
            <label className="building-form-wide">Motivo de la corrección<textarea name="reason" maxLength={500} rows={3} required /></label>
          </fieldset>
          {volume !== undefined && (
            <fieldset disabled={saving} className="building-form">
              <legend>Lecturas del contador</legend>
              <p>Las lecturas deben coincidir con las facturas anterior y siguiente de cada unidad, cuando existan.</p>
              <VolumeField value={volume} />
              {invoice.charges.map(({ meter, unit_id, unit_number }) => meter && (
                <ReadingFields key={unit_id} meter={{ unit_id, unit_number, previous_reading: null }} saved={meter} />
              ))}
            </fieldset>
          )}
          {error && <p role="alert" className="form-error">{error}</p>}
          <div className="building-form-actions">
            <button type="submit" disabled={saving}>{saving ? 'Guardando…' : 'Guardar corrección'}</button>
            <button type="button" onClick={close} disabled={saving}>Cancelar</button>
            {error && <button type="button" onClick={onReload} disabled={saving}>Recargar ficha</button>}
          </div>
        </form>
      )}
      {invoice.corrections.length > 0 && (
        <dl className="building-details" aria-label="Historial de correcciones">
          {invoice.corrections.map(({ revision, reason, corrected_by, corrected_at }) => (
            <div key={revision}>
              <dt>Corrección {revision}</dt>
              <dd>{reason}</dd>
              <dd>{corrected_by} · <time dateTime={corrected_at}>{new Date(corrected_at).toLocaleString('es-PE')}</time></dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  )
}
