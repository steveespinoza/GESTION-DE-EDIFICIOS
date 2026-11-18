import { useEffect, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'

import { PropertyRequestError } from '../properties/api'
import type { Period } from './api'
import { periodLabel } from './format'

const periodKey = (item: Period) => `${item.billing_year}-${String(item.billing_month).padStart(2, '0')}`

export function ConsolidationPanel({ buildingId, periods }: { buildingId: string; periods: Period[] }) {
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
    try {
      const response = await fetch(`/api/admin/buildings/${encodeURIComponent(buildingId)}/consolidation.pdf?billing_year=${period.billing_year}&billing_month=${period.billing_month}`, {
        signal: AbortSignal.any([abort.signal, AbortSignal.timeout(30_000)]),
      })
      if (!response.ok) throw new PropertyRequestError(response.status)
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = url
      link.download = `consolidado-${periodKey(period)}-${buildingId.slice(0, 8)}.pdf`
      document.body.append(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
      setSaved(`PDF consolidado de ${periodLabel(period)} preparado para descargar.`)
    } catch (issue) {
      if (abort.signal.aborted) return
      if (issue instanceof PropertyRequestError && issue.status === 401) endSession()
      else if (issue instanceof PropertyRequestError && issue.status === 409) setError('El periodo ya no tiene cargos. Actualiza las cobranzas para elegir otro.')
      else if (issue instanceof PropertyRequestError && [403, 404].includes(issue.status)) setError('El edificio no está disponible para tu cuenta.')
      else setError('No se pudo descargar el consolidado. Vuelve a intentar.')
    } finally {
      if (!abort.signal.aborted) setSaving(false)
    }
  }

  return (
    <section className="building-surface" aria-labelledby="consolidation-title" aria-busy={saving}>
      <h2 id="consolidation-title">PDF consolidado mensual</h2>
      <p>Incluye las facturas del mes y los cargos, pagos aplicados, saldos anteriores y crédito de todas las unidades del edificio. Refleja los movimientos vigentes al descargar.</p>
      <p>El periodo del PDF se elige aquí. Los filtros de la lista de cobranzas se aplican solo a esa lista.</p>
      {period ? <div className="building-form">
        <label className="report-input">Periodo del consolidado<select value={periodKey(period)} disabled={saving} onChange={(event) => { setSelected(event.target.value); setSaved(''); setError('') }}>
          {options.map(([key, item]) => <option key={key} value={key}>{periodLabel(item)}</option>)}
        </select></label>
        <div className="building-form-actions"><button type="button" disabled={saving} onClick={download}>{saving ? 'Preparando consolidado…' : 'Descargar PDF consolidado'}</button></div>
      </div> : <p>No hay periodos con cargos para consolidar.</p>}
      {(saved || error) && <p ref={notice} role={error ? 'alert' : 'status'} tabIndex={-1}>{error || saved}</p>}
    </section>
  )
}
