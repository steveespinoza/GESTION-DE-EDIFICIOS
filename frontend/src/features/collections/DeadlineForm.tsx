import { useRef, useState, type FormEvent } from 'react'
import { useOutletContext } from 'react-router-dom'

import { PropertyRequestError } from '../properties/api'
import type { Period } from './api'
import { saveDeadline, type Deadline } from './deadlineApi'
import { periodLabel } from './format'

interface Props {
  buildingId: string
  period: Period
  current?: Deadline
  onSaved: (deadline: Deadline) => void
  refresh: () => void
}

export function DeadlineForm({ buildingId, period, current, onSaved, refresh }: Props) {
  const endSession = useOutletContext<() => void>()
  const request = useRef<{ values: string; id: string } | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [conflict, setConflict] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (saving) return
    const fields = new FormData(event.currentTarget)
    const values = { ...period, revision: current?.revision ?? 0, due_date: String(fields.get('due_date')), reason: String(fields.get('reason')).trim() }
    const serialized = JSON.stringify(values)
    if (request.current?.values !== serialized) request.current = { values: serialized, id: crypto.randomUUID() }
    setSaving(true)
    setError('')
    setConflict(false)
    try {
      onSaved(await saveDeadline(buildingId, { ...values, request_id: request.current.id }))
    } catch (issue) {
      if (issue instanceof PropertyRequestError && issue.status === 401) endSession()
      else if (issue instanceof PropertyRequestError && issue.status === 409) {
        setError(issue.detail ?? 'El vencimiento cambió. Actualiza las cobranzas.')
        setConflict(true)
      } else if (issue instanceof PropertyRequestError && issue.status === 422) setError('Revisa la fecha y el motivo.')
      else setError('No se pudo confirmar el vencimiento. Reintenta con los mismos datos o actualiza el historial.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="building-form" onSubmit={submit} aria-busy={saving}>
      <p>Fecha común para todas las unidades y servicios de {periodLabel(period)}. {current ? `Revisión vigente: ${current.revision}.` : 'Todavía no tiene vencimiento.'}</p>
      <fieldset className="building-form-grid" disabled={saving}>
        <legend>Vencimiento del periodo</legend>
        <label>Fecha límite de pago<input type="date" name="due_date" defaultValue={current?.due_date ?? ''} required /></label>
        <label>Motivo<input name="reason" maxLength={500} required /></label>
      </fieldset>
      {error && <p role="alert">{error}</p>}
      <div className="building-form-actions">
        <button type="submit" disabled={saving}>{saving ? 'Guardando…' : 'Guardar vencimiento'}</button>
        {conflict && <button type="button" disabled={saving} onClick={refresh}>Actualizar cobranzas</button>}
      </div>
    </form>
  )
}
