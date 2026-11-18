import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { useOutletContext } from 'react-router-dom'

import { PropertyRequestError } from '../properties/api'
import { usePropertyQuery } from '../properties/usePropertyQuery'
import type { Period } from './api'
import { issueReceipt, listReceipts, receiptDownload, type Receipt } from './receiptApi'
import { money, periodLabel } from './format'

const periodKey = (item: Period) => `${item.billing_year}-${String(item.billing_month).padStart(2, '0')}`

function ReceiptIssueForm({ buildingId, unitId, period, latest, onSaved, refresh }: { buildingId: string; unitId: string; period: Period; latest?: Receipt; onSaved: (item: Receipt) => void; refresh: () => void }) {
  const endSession = useOutletContext<() => void>()
  const request = useRef<{ values: string; id: string } | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [conflict, setConflict] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (saving) return
    const fields = new FormData(event.currentTarget)
    const input = { ...period, revision: latest?.version ?? 0, reason: String(fields.get('reason')).trim() }
    const values = JSON.stringify(input)
    if (request.current?.values !== values) request.current = { values, id: crypto.randomUUID() }
    setSaving(true)
    setError('')
    setConflict(false)
    try {
      onSaved(await issueReceipt(unitId, buildingId, { ...input, request_id: request.current.id }))
    } catch (issue) {
      if (issue instanceof PropertyRequestError && issue.status === 401) endSession()
      else if (issue instanceof PropertyRequestError && issue.status === 409) {
        setError(issue.detail ?? 'El recibo cambió. Actualiza el historial.')
        setConflict(true)
      } else if (issue instanceof PropertyRequestError && issue.status === 422) setError('Revisa el periodo y el motivo.')
      else if (issue instanceof PropertyRequestError && issue.status === 503) setError('No se pudo guardar el PDF. Reintenta con los mismos datos.')
      else setError('No se pudo confirmar la emisión. Reintenta con los mismos datos o actualiza el historial.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="building-form" onSubmit={submit} aria-busy={saving}>
      <label>Motivo de emisión<input name="reason" maxLength={500} required defaultValue={latest ? '' : 'Emisión inicial'} disabled={saving} /></label>
      {error && <p role="alert">{error}</p>}
      <div className="building-form-actions">
        <button type="submit" disabled={saving}>{saving ? 'Emitiendo…' : latest ? 'Emitir nueva versión' : 'Emitir recibo PDF'}</button>
        {conflict && <button type="button" disabled={saving} onClick={refresh}>Actualizar historial de recibos</button>}
      </div>
    </form>
  )
}

export function ReceiptsPanel({ unitId, buildingId, periods }: { unitId: string; buildingId?: string; periods: Period[] }) {
  const load = useCallback((signal: AbortSignal) => listReceipts(unitId, buildingId, signal), [unitId, buildingId])
  const { query, retry } = usePropertyQuery(load)
  const [selected, setSelected] = useState('')
  const [saved, setSaved] = useState<Receipt>()
  const notice = useRef<HTMLParagraphElement>(null)
  useEffect(() => { if (saved && query.status === 'ready') notice.current?.focus() }, [saved, query.status])
  const options = [...new Map([...periods, ...(query.status === 'ready' ? query.data : [])].map((item) => [periodKey(item), item])).entries()].sort(([a], [b]) => b.localeCompare(a))
  const period = options.find(([key]) => key === selected)?.[1] ?? options[0]?.[1]
  const receipts = query.status === 'ready' ? query.data.filter((item) => period && periodKey(item) === periodKey(period)) : []
  const latest = receipts[0]

  return (
    <section className="building-surface receipt-panel" aria-labelledby="receipts-title">
      <h2 id="receipts-title">Recibos PDF</h2>
      <p>El recibo conserva los importes y la fecha límite al emitirlo. Los movimientos posteriores se consultan en el estado de cuenta actual.</p>
      {saved && <p ref={notice} role="status" tabIndex={-1}>Recibo de {periodLabel(saved)}, versión {saved.version}, emitido.</p>}
      {query.status === 'loading' && <p role="status">Cargando recibos…</p>}
      {query.status === 'error' && <div><p role="alert">No se pudo cargar el historial de recibos.</p><button type="button" onClick={retry}>Volver a intentar</button></div>}
      {query.status === 'ready' && (
        <>
          {period && <label className="building-form">Periodo del recibo<select value={periodKey(period)} onChange={(event) => setSelected(event.target.value)}>{options.map(([key, item]) => <option key={key} value={key}>{periodLabel(item)}</option>)}</select></label>}
          {receipts.length === 0 ? <p>Todavía no hay recibos emitidos para este periodo.{!buildingId && ' La administración puede emitirlo desde esta unidad.'}</p> : (
            <ul className="receipt-history building-details">
              {receipts.map((item) => (
                <li key={item.id}>
                  <a href={receiptDownload(unitId, buildingId, item.id)} target="_blank" rel="noreferrer">Descargar PDF · {periodLabel(item)} · Versión {item.version}</a>
                  <p>Pendiente al emitir: {money(item.total_pending)} · Vencimiento: {item.due_date ?? 'Sin vencimiento'}</p>
                  <p>{item.reason} · {item.issued_by} · <time dateTime={item.issued_at}>{new Date(item.issued_at).toLocaleString('es-PE')}</time></p>
                </li>
              ))}
            </ul>
          )}
          {buildingId && period && <ReceiptIssueForm key={`${periodKey(period)}:${latest?.version ?? 0}`} buildingId={buildingId} unitId={unitId} period={{billing_year:period.billing_year,billing_month:period.billing_month}} latest={latest} refresh={retry} onSaved={(item) => { setSaved(item); setSelected(periodKey(item)); retry() }} />}
        </>
      )}
    </section>
  )
}
