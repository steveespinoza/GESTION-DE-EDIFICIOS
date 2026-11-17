import { useCallback, useRef, useState, type FormEvent } from 'react'
import { useOutletContext } from 'react-router-dom'

import { PropertyRequestError } from '../properties/api'
import { usePropertyQuery } from '../properties/usePropertyQuery'
import type { Period } from './api'
import { money, periodLabel } from './format'
import { PaymentFields, PaymentPeriodFields, readPaymentPeriod, readPaymentValues } from './PaymentFields'
import { ownerReports, proofDownload, reportStatus, submitReport } from './reportApi'

export function OwnerReports({ unitId, period }: { unitId: string; period?: Period }) {
  const onSessionEnded = useOutletContext<() => void>()
  const load = useCallback((signal: AbortSignal) => ownerReports(unitId, signal), [unitId])
  const { query, retry } = usePropertyQuery(load)
  const requestId = useRef<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [feedback, setFeedback] = useState<{ error: boolean; message: string }>()

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (saving) return
    const form = event.currentTarget
    const fields = new FormData(form)
    const proof = fields.get('proof')
    if (!(proof instanceof File) || !proof.size || proof.size > 10 * 1024 * 1024) {
      setFeedback({ error: true, message: 'Elige un comprobante de hasta 10 MiB.' })
      return
    }
    requestId.current ??= crypto.randomUUID()
    setSaving(true)
    setFeedback(undefined)
    try {
      await submitReport(unitId, {
        request_id: requestId.current,
        ...readPaymentPeriod(fields),
        ...readPaymentValues(fields),
      }, proof)
      requestId.current = null
      form.reset()
      setFeedback({ error: false, message: 'Reporte enviado. Revisa su estado en el historial.' })
      retry()
    } catch (issue) {
      if (issue instanceof PropertyRequestError && issue.status === 401) {
        onSessionEnded()
        return
      }
      const message = issue instanceof PropertyRequestError && issue.detail
        ? issue.detail
        : 'No se pudo confirmar el envío. Revisa el historial antes de intentarlo de nuevo.'
      setFeedback({ error: true, message })
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="building-surface" aria-labelledby="owner-reports-title">
      <h2 id="owner-reports-title">Reportar un pago</h2>
      <form className="building-form" onSubmit={submit} aria-busy={saving}>
        <fieldset className="building-form-grid" disabled={saving}>
          <legend>Pago realizado</legend>
          <PaymentPeriodFields period={period} />
          <PaymentFields reported />
          <label className="building-form-wide">
            Comprobante (PDF, PNG o JPEG, hasta 10 MiB)
            <input name="proof" type="file" accept=".pdf,.png,.jpg,.jpeg" required />
          </label>
        </fieldset>
        <p>El saldo se actualiza cuando administración aprueba el pago.</p>
        {feedback && <p role={feedback.error ? 'alert' : 'status'}>{feedback.message}</p>}
        <button type="submit" disabled={saving}>{saving ? 'Enviando…' : 'Enviar reporte'}</button>
      </form>
      <div className="payment-report-history">
        <h3>Reportes enviados</h3>
        {query.status === 'loading' && <p role="status">Cargando reportes…</p>}
        {query.status === 'error' && (
          <>
            <p role="alert">No se pudieron cargar los reportes.</p>
            <button type="button" onClick={retry}>Volver a intentar</button>
          </>
        )}
        {query.status === 'ready' && (query.data.length === 0 ? <p>Todavía no hay reportes enviados.</p> : (
          <dl className="building-details">
            {query.data.map((report) => (
              <div key={report.id}>
                <dt>{periodLabel(report)} · {money(report.amount)}</dt>
                <dd>{reportStatus[report.status]}</dd>
                {report.rejection_reason && <dd>Motivo del rechazo · {report.rejection_reason}</dd>}
                <dd><a href={proofDownload(report)}>{report.filename}</a></dd>
              </div>
            ))}
          </dl>
        ))}
      </div>
    </section>
  )
}
