import { useEffect, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'

import { PropertyRequestError } from '../properties/api'
import type { Period } from './api'
import { periodLabel } from './format'

const periodKey = (item: Period) => `${item.billing_year}-${String(item.billing_month).padStart(2, '0')}`

export function TransparencyPanel({ unitId, buildingId, periods }: { unitId: string; buildingId?: string; periods: Period[] }) {
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

  async function download() {
    if (!period || saving) return
    setSaving(true)
    setSaved('')
    setError('')
    const abort = new AbortController()
    controller.current = abort
    const base = buildingId
      ? `/api/admin/buildings/${encodeURIComponent(buildingId)}/units/${encodeURIComponent(unitId)}`
      : `/api/owner/properties/${encodeURIComponent(unitId)}`
    try {
      const response = await fetch(`${base}/transparency.xlsx?billing_year=${period.billing_year}&billing_month=${period.billing_month}`, {
        signal: AbortSignal.any([abort.signal, AbortSignal.timeout(30_000)]),
      })
      if (!response.ok) throw new PropertyRequestError(response.status)
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `transparencia-${periodKey(period)}-${unitId.slice(0, 8)}.xlsx`
      document.body.append(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
      setSaved(`Excel de ${periodLabel(period)} preparado para descargar.`)
    } catch (issue) {
      if (abort.signal.aborted) return
      if (issue instanceof PropertyRequestError && issue.status === 401) endSession()
      else if (issue instanceof PropertyRequestError && issue.status === 409) setError('El periodo ya no tiene cargos. Actualiza el estado de cuenta para elegir otro.')
      else if (issue instanceof PropertyRequestError && [403, 404].includes(issue.status)) setError('La unidad ya no está disponible para tu cuenta.')
      else setError('No se pudo descargar el Excel. Vuelve a intentar.')
    } finally {
      if (!abort.signal.aborted) setSaving(false)
    }
  }

  return (
    <section className="building-surface" aria-labelledby="transparency-title" aria-busy={saving}>
      <h2 id="transparency-title">Excel de transparencia</h2>
      <p>Consulta el reparto de cada servicio, las lecturas de esta unidad y sus pagos y ajustes. El pendiente incluye el periodo elegido y los saldos anteriores, con los movimientos vigentes al descargar.</p>
      {period ? <div className="building-form">
        <label>Periodo del Excel<select value={periodKey(period)} disabled={saving} onChange={(event) => { setSelected(event.target.value); setSaved(''); setError('') }}>
          {options.map(([key, item]) => <option key={key} value={key}>{periodLabel(item)}</option>)}
        </select></label>
        <div className="building-form-actions"><button type="button" disabled={saving} onClick={download}>{saving ? 'Preparando Excel…' : 'Descargar Excel de transparencia'}</button></div>
      </div> : <p>No hay periodos con cargos para exportar.</p>}
      {(saved || error) && <p ref={notice} role={error ? 'alert' : 'status'} tabIndex={-1}>{error || saved}</p>}
    </section>
  )
}
