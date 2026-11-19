import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { useOutletContext } from 'react-router-dom'

import { PropertyRequestError } from '../properties/api'
import { usePropertyQuery } from '../properties/usePropertyQuery'
import { readCollections, type CollectionOverview } from './deadlineApi'
import { periodLabel } from './format'
import { prepareBatch, type Batch } from './batchApi'

const periodKey = (item: { billing_year: number; billing_month: number }) => `${item.billing_year}-${String(item.billing_month).padStart(2, '0')}`

function CreateForm({ buildingId, context, onPrepared, onPreparing, disabled, refresh }: { buildingId: string; context: CollectionOverview; onPrepared: (batch: Batch) => Promise<void>; onPreparing: (busy: boolean) => void; disabled: boolean; refresh: () => void }) {
  const endSession = useOutletContext<() => void>()
  const [selected, setSelected] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [conflict, setConflict] = useState(false)
  const request = useRef<{ values: string; id: string } | null>(null)
  const controller = useRef<AbortController | null>(null)
  useEffect(() => () => controller.current?.abort(), [])
  const periods = [...new Map(context.rows.map((row) => [periodKey(row), row])).entries()].sort(([a], [b]) => b.localeCompare(a))
  const period = periods.find(([key]) => key === selected)?.[1] ?? periods[0]?.[1]
  const deadline = context.deadlines.find((item) => period && periodKey(item) === periodKey(period))

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (saving || disabled || !period) return
    const fields = new FormData(event.currentTarget)
    const values = { billing_year: period.billing_year, billing_month: period.billing_month, deadline_revision: deadline?.revision ?? 0, due_date: String(fields.get('due_date')), reason: String(fields.get('reason')).trim() }
    const serialized = JSON.stringify(values)
    if (request.current?.values !== serialized) request.current = { values: serialized, id: crypto.randomUUID() }
    setSaving(true)
    onPreparing(true)
    setError('')
    setConflict(false)
    const abort = new AbortController()
    controller.current = abort
    try {
      const batch = await prepareBatch(buildingId, { ...values, request_id: request.current.id }, abort.signal)
      if (abort.signal.aborted) return
      await onPrepared(batch)
    } catch (issue) {
      if (abort.signal.aborted) return
      if (issue instanceof PropertyRequestError && issue.status === 401) endSession()
      else if (issue instanceof PropertyRequestError && issue.status === 409) {
        setError(issue.detail ?? 'Los datos cambiaron. Actualiza antes de preparar el lote.')
        setConflict(true)
      } else if (issue instanceof PropertyRequestError && issue.status === 422) setError('Revisa el periodo, el vencimiento y el motivo.')
      else setError('No se pudo confirmar la preparación. Reintenta con los mismos datos o consulta el historial antes de crear otro lote.')
    } finally { if (!abort.signal.aborted) { setSaving(false); onPreparing(false) } }
  }

  return <section className="building-surface" aria-labelledby="new-batch-title">
    <h2 id="new-batch-title">Preparar un lote</h2>
    <p>Se emitirá una versión nueva por unidad con cargos del periodo. Los recibos existentes se conservan. Las unidades sin cargos se mostrarán como omitidas.</p>
    {period ? <form className="building-form" onSubmit={submit} aria-busy={saving}>
      <fieldset className="building-form-grid" disabled={saving || disabled}>
        <legend>Periodo y vencimiento común</legend>
        <label>Periodo del lote<select value={periodKey(period)} onChange={(event) => { setSelected(event.target.value); setError(''); setConflict(false) }}>{periods.map(([key, item]) => <option key={key} value={key}>{periodLabel(item)}</option>)}</select></label>
        <label>Fecha límite de pago<input key={periodKey(period)} type="date" name="due_date" required defaultValue={deadline?.due_date ?? ''} /></label>
        <label className="building-form-wide">Motivo de emisión<input name="reason" maxLength={500} required /></label>
      </fieldset>
      <p>Esta fecha será el vencimiento común del periodo en todo el edificio. Si ya coincide, se conserva la revisión vigente.</p>
      {error && <p role="alert">{error}</p>}
      <div className="building-form-actions"><button type="submit" disabled={saving || disabled}>{saving ? 'Preparando lote…' : 'Emitir recibos del periodo'}</button>{conflict && <button type="button" disabled={saving || disabled} onClick={refresh}>Actualizar datos del lote</button>}</div>
    </form> : <p>No hay periodos con cargos para emitir recibos.</p>}
  </section>
}

export function ReceiptBatchForm({ buildingId, onPrepared, onPreparing, disabled }: { buildingId: string; onPrepared: (batch: Batch) => Promise<void>; onPreparing: (busy: boolean) => void; disabled: boolean }) {
  const load = useCallback((signal: AbortSignal) => readCollections(buildingId, signal), [buildingId])
  const { query, retry } = usePropertyQuery(load)
  if (query.status === 'loading') return <p role="status">Cargando periodos y vencimientos…</p>
  if (query.status === 'error') return <div><p role="alert">No se pudieron cargar los datos para preparar un lote.</p><button type="button" onClick={retry}>Volver a intentar</button></div>
  return <CreateForm buildingId={buildingId} context={query.data} onPrepared={onPrepared} onPreparing={onPreparing} disabled={disabled} refresh={retry} />
}
