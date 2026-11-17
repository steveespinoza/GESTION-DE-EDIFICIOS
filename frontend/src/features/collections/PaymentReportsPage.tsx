import { useCallback, useRef, useState, type FormEvent } from 'react'
import { Link, useOutletContext, useParams } from 'react-router-dom'

import { PropertyRequestError, readBuilding } from '../properties/api'
import { usePropertyQuery } from '../properties/usePropertyQuery'
import { money, periodLabel } from './format'
import { PaymentFields, readPaymentValues } from './PaymentFields'
import { approveReport, buildingReports, replaceProof, rejectReport, reportStatus, type PaymentReport } from './reportApi'
import { ProofHistory } from './ProofHistory'
import './collections.css'

function ReviewForms({ buildingId, report, onReviewed, onReplaced }: {
  buildingId: string
  report: PaymentReport
  onReviewed: (report: PaymentReport) => void
  onReplaced: () => void
}) {
  const onSessionEnded = useOutletContext<() => void>()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const requestId = useRef<string | null>(null)

  async function replace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (saving) return
    const fields = new FormData(event.currentTarget)
    const file = fields.get('proof')
    const reason = String(fields.get('replacement_reason') ?? '').trim()
    if (!(file instanceof File) || !file.size || file.size > 10 * 1024 * 1024 || !reason) {
      setError('Selecciona un comprobante de hasta 10 MiB e indica el motivo del reemplazo.')
      return
    }
    requestId.current ??= crypto.randomUUID()
    setSaving(true)
    setError('')
    try {
      await replaceProof(buildingId, report, requestId.current, reason, file)
      onReplaced()
    } catch (issue) {
      if (issue instanceof PropertyRequestError && issue.status === 401) onSessionEnded()
      else setError(issue instanceof PropertyRequestError && issue.detail ? issue.detail : 'No se pudo confirmar el reemplazo. Actualiza el reporte para comprobar el historial.')
    } finally {
      setSaving(false)
    }
  }

  async function review(event: FormEvent<HTMLFormElement>, approval: boolean) {
    event.preventDefault()
    if (saving) return
    const fields = new FormData(event.currentTarget)
    setSaving(true)
    setError('')
    try {
      const result = approval
        ? await approveReport(buildingId, report.id, { ...readPaymentValues(fields), proof_revision: report.proof_revision })
        : await rejectReport(buildingId, report.id, String(fields.get('reason')), report.proof_revision)
      onReviewed(result)
    } catch (issue) {
      if (issue instanceof PropertyRequestError && issue.status === 401) onSessionEnded()
      else setError(issue instanceof PropertyRequestError && issue.detail ? issue.detail : 'No se pudo confirmar la revisión. Actualiza la bandeja para comprobar el estado.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="payment-review-forms">
      <form className="building-form" onSubmit={(event) => void replace(event)} aria-busy={saving}>
        <fieldset className="building-form-grid" disabled={saving}>
          <legend>Reemplazar comprobante</legend>
          <label className="building-form-wide">Nuevo comprobante (PDF, PNG o JPEG, hasta 10 MiB)<input type="file" name="proof" accept=".pdf,.png,.jpg,.jpeg" required /></label>
          <label className="building-form-wide">Motivo del reemplazo<textarea name="replacement_reason" rows={2} maxLength={500} required /></label>
        </fieldset>
        <button type="submit" disabled={saving}>Guardar nuevo comprobante</button>
      </form>
      <form className="building-form" onSubmit={(event) => void review(event, true)} aria-busy={saving}>
        <fieldset className="building-form-grid" disabled={saving}>
          <legend>Confirmar datos del pago</legend>
          <PaymentFields values={report} />
        </fieldset>
        <button type="submit" disabled={saving}>Aprobar y aplicar pago</button>
      </form>
      <form className="building-form" onSubmit={(event) => void review(event, false)} aria-busy={saving}>
        <label className="report-input">Motivo del rechazo<textarea name="reason" rows={2} maxLength={500} disabled={saving} required /></label>
        <button type="submit" disabled={saving}>Rechazar reporte</button>
      </form>
      {error && <p role="alert">{error}</p>}
    </div>
  )
}

function BuildingReports({ buildingId }: { buildingId: string }) {
  const load = useCallback(async (signal: AbortSignal) => {
    const [building, reports] = await Promise.all([readBuilding(buildingId, signal), buildingReports(buildingId, signal)])
    return { building, reports }
  }, [buildingId])
  const { query, retry } = usePropertyQuery(load)
  const [selected, setSelected] = useState('PENDING')
  const [notice, setNotice] = useState('')
  const visible = query.status === 'ready' ? query.data.reports.filter((item) => !selected || item.status === selected) : []
  const buildingPath = `/admin/edificios/${buildingId}`

  function onReviewed(report: PaymentReport) {
    setNotice(report.status === 'APPROVED' ? 'Reporte aprobado. El pago quedó aplicado.' : 'Reporte rechazado.')
    retry()
  }

  function onReplaced() {
    setNotice('Comprobante reemplazado. La versión anterior está disponible en el historial.')
    retry()
  }

  return (
    <section className="building-page unit-statement" aria-labelledby="reports-title">
      <Link to={buildingPath}>Volver al edificio</Link>
      <h1 id="reports-title">Reportes de pago</h1>
      {notice && <p role="status">{notice}</p>}
      {query.status === 'loading' && <p role="status">Cargando reportes…</p>}
      {query.status === 'error' && (
        <div>
          <p role="alert">{query.error instanceof PropertyRequestError && query.error.status === 404 ? 'No se encontró el edificio.' : 'No se pudieron cargar los reportes.'}</p>
          <button type="button" onClick={retry}>Volver a intentar</button>
        </div>
      )}
      {query.status === 'ready' && (
        <>
          <p>{query.data.building.name}</p>
          <div className="building-form-actions">
            <div className="building-form report-status-filter">
              <label htmlFor="report-status-filter">Estado</label>
              <select id="report-status-filter" value={selected} onChange={(event) => setSelected(event.target.value)}>
                <option value="">Todos los reportes</option>
                {Object.entries(reportStatus).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </div>
            <button type="button" onClick={retry}>Actualizar reportes</button>
          </div>
          {visible.length === 0 && <p>No hay reportes para el estado seleccionado.</p>}
          {visible.map((report) => (
            <details className="building-surface" key={report.id}>
              <summary>Unidad {report.unit_number} · {periodLabel(report)} · {money(report.amount)}</summary>
              <div className="payment-review-forms">
                <p>{reportStatus[report.status]} · Fecha declarada {report.received_on}</p>
                {report.reference && <p>Referencia declarada {report.reference}</p>}
                {report.rejection_reason && <p>Motivo del rechazo · {report.rejection_reason}</p>}
                <ProofHistory report={report} buildingId={buildingId} />
                <Link to={`${buildingPath}/unidades/${report.unit_id}/estado-de-cuenta`}>Ver estado de cuenta</Link>
                {report.status === 'PENDING' && <ReviewForms buildingId={buildingId} report={report} onReviewed={onReviewed} onReplaced={onReplaced} />}
              </div>
            </details>
          ))}
        </>
      )}
    </section>
  )
}

export function PaymentReportsPage() {
  const { buildingId } = useParams()
  return buildingId ? <BuildingReports key={buildingId} buildingId={buildingId} /> : null
}
