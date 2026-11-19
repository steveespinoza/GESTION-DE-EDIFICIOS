import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useOutletContext } from 'react-router-dom'

import { PropertyRequestError } from '../properties/api'
import type { Period } from './api'
import { periodLabel } from './format'

const periodKey = (item: Period) => `${item.billing_year}-${String(item.billing_month).padStart(2, '0')}`

export function MonthlyExcelPanel({ buildingId, periods }: { buildingId: string; periods: Period[] }) {
  const endSession = useOutletContext<() => void>()
  const [selected, setSelected] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')
  const controller = useRef<AbortController | null>(null)
  const notice = useRef<HTMLParagraphElement>(null)
  useEffect(() => () => controller.current?.abort(), [])
  useEffect(() => { if (saved || error) notice.current?.focus() }, [saved, error])
  const options = [...new Map(periods.map((item) => [periodKey(item), item])).entries()].sort(([a], [b]) => b.localeCompare(a))
  const period = options.find(([key]) => key === selected)?.[1] ?? options[0]?.[1]

  async function download(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!period || saving) return
    setSaving(true)
    setSaved('')
    setError('')
    const abort = new AbortController()
    controller.current = abort
    try {
      const response = await fetch(`/api/admin/buildings/${encodeURIComponent(buildingId)}/monthly.xlsx?billing_year=${period.billing_year}&billing_month=${period.billing_month}`, {
        signal: AbortSignal.any([abort.signal, AbortSignal.timeout(30_000)]),
      })
      if (!response.ok) throw new PropertyRequestError(response.status)
      const body = await response.blob()
      if (abort.signal.aborted) return
      const url = URL.createObjectURL(body)
      const link = document.createElement('a')
      link.href = url
      link.download = `mensual-${periodKey(period)}-${buildingId.slice(0, 8)}.xlsx`
      document.body.append(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
      setSaved(`Excel mensual de ${periodLabel(period)} preparado para descargar.`)
    } catch (issue) {
      if (abort.signal.aborted) return
      if (issue instanceof PropertyRequestError && issue.status === 401) endSession()
      else if (issue instanceof PropertyRequestError && issue.status === 409) setError('El periodo ya no tiene cargos. Actualiza las cobranzas para elegir otro.')
      else if (issue instanceof PropertyRequestError && [403, 404].includes(issue.status)) setError('El edificio no está disponible para tu cuenta.')
      else setError('No se pudo descargar el Excel mensual. Vuelve a intentar.')
    } finally { if (!abort.signal.aborted) setSaving(false) }
  }

  return <section className="building-surface" aria-labelledby="monthly-excel-title" aria-busy={saving}>
    <h2 id="monthly-excel-title">Excel mensual del edificio</h2>
    <p>Consolidado por unidad y servicio, matriz de reparto y detalle de consumos, cargos y pagos aplicados. Incluye todas las unidades y conserva el reparto original de cada factura.</p>
    <p>Refleja los movimientos vigentes al descargar. El periodo del Excel se elige aquí; los filtros de la lista de cobranzas se aplican solo a esa lista.</p>
    {period ? <form className="building-form" onSubmit={download}>
      <label className="report-input">Periodo del Excel mensual<select value={periodKey(period)} disabled={saving} onChange={(event) => { setSelected(event.target.value); setSaved(''); setError('') }}>
        {options.map(([key, item]) => <option key={key} value={key}>{periodLabel(item)}</option>)}
      </select></label>
      <div className="building-form-actions"><button type="submit" disabled={saving}>{saving ? 'Preparando Excel mensual…' : 'Descargar Excel mensual'}</button></div>
    </form> : <p>No hay periodos con cargos para exportar el Excel mensual.</p>}
    {(saved || error) && <p ref={notice} role={error ? 'alert' : 'status'} tabIndex={-1}>{error || saved}</p>}
  </section>
}
