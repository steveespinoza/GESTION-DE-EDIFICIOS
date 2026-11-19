import { useEffect, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'

import { PropertyRequestError } from '../properties/api'

export function CollectionHistoryPanel({ buildingId, hasPeriods }: { buildingId: string; hasPeriods: boolean }) {
  const endSession = useOutletContext<() => void>()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')
  const controller = useRef<AbortController | null>(null)
  const notice = useRef<HTMLParagraphElement>(null)
  useEffect(() => () => controller.current?.abort(), [])
  useEffect(() => { if (saved || error) notice.current?.focus() }, [saved, error])

  async function download() {
    if (saving || !hasPeriods) return
    setSaving(true)
    setSaved('')
    setError('')
    const abort = new AbortController()
    controller.current = abort
    try {
      const response = await fetch(`/api/admin/buildings/${encodeURIComponent(buildingId)}/collections.xlsx`, {
        signal: AbortSignal.any([abort.signal, AbortSignal.timeout(30_000)]),
      })
      if (!response.ok) throw new PropertyRequestError(response.status)
      const body = await response.blob()
      if (abort.signal.aborted) return
      const url = URL.createObjectURL(body)
      const link = document.createElement('a')
      link.href = url
      link.download = `cobranzas-${buildingId.slice(0, 8)}.xlsx`
      document.body.append(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
      setSaved('Excel histórico de cobranzas preparado para descargar.')
    } catch (issue) {
      if (abort.signal.aborted) return
      if (issue instanceof PropertyRequestError && issue.status === 401) endSession()
      else if (issue instanceof PropertyRequestError && issue.status === 409) setError('El edificio ya no tiene periodos con cargos. Actualiza las cobranzas.')
      else if (issue instanceof PropertyRequestError && [403, 404].includes(issue.status)) setError('El edificio no está disponible para tu cuenta.')
      else setError('No se pudo descargar el histórico de cobranzas. Vuelve a intentar.')
    } finally { if (!abort.signal.aborted) setSaving(false) }
  }

  return <section className="building-surface" aria-labelledby="collection-history-title" aria-busy={saving}>
    <h2 id="collection-history-title">Excel histórico de cobranzas</h2>
    <p>Un resumen y una hoja por periodo, con cargos, aplicaciones de pagos y saldos por unidad. Los pendientes anteriores se muestran separados; el resumen cuenta cada saldo una sola vez.</p>
    <p>Incluye todos los periodos registrados y los movimientos vigentes al descargar. Los filtros de la lista no reducen el archivo.</p>
    {hasPeriods ? <div className="building-form-actions"><button type="button" disabled={saving} onClick={download}>{saving ? 'Preparando histórico…' : 'Descargar Excel histórico de cobranzas'}</button></div> : <p>No hay periodos con cargos para exportar el histórico.</p>}
    {(saved || error) && <p ref={notice} role={error ? 'alert' : 'status'} tabIndex={-1}>{error || saved}</p>}
  </section>
}
