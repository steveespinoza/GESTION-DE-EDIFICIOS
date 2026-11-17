import { useCallback } from 'react'

import { usePropertyQuery } from '../properties/usePropertyQuery'
import { proofDownload, proofHistory, type PaymentReport } from './reportApi'

export function ProofHistory({ report, buildingId }: { report: PaymentReport; buildingId?: string }) {
  const load = useCallback(
    (signal: AbortSignal) => proofHistory(report, signal, buildingId),
    [report, buildingId],
  )
  const { query, retry } = usePropertyQuery(load)
  if (query.status === 'loading') return <p role="status">Cargando comprobantes…</p>
  if (query.status === 'error') {
    return (
      <div>
        <p role="alert">No se pudieron cargar las versiones del comprobante.</p>
        <button type="button" onClick={retry}>Volver a cargar comprobantes</button>
      </div>
    )
  }
  const current = query.data.at(-1)?.revision

  return (
    <div className="proof-history">
      <h4>Versiones del comprobante</h4>
      <dl className="building-details">
        {query.data.map((proof) => (
          <div key={proof.revision}>
            <dt>{proof.revision === 0 ? 'Original' : `Versión ${proof.revision}`}{proof.revision === current && ' · Vigente'}</dt>
            <dd><a href={proofDownload(report, buildingId, proof.revision)}>{buildingId ? 'Descargar ' : ''}{proof.filename}</a></dd>
            <dd>{proof.uploaded_by} · <time dateTime={proof.uploaded_at}>{new Date(proof.uploaded_at).toLocaleString('es-PE')}</time></dd>
            {proof.reason && <dd>Motivo · {proof.reason}</dd>}
          </div>
        ))}
      </dl>
    </div>
  )
}
