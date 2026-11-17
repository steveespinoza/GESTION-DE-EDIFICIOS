import { propertyRequest, writeProperty } from '../properties/api'
import type { PaymentInput, PaymentValues, Period } from './api'

export type ReportStatus = 'PENDING' | 'APPROVED' | 'REJECTED'
export interface PaymentReport extends Period, PaymentValues {
  id: string
  unit_id: string
  unit_number: string
  status: ReportStatus
  filename: string
  submitted_at: string
  reviewed_at: string | null
  payment_id: string | null
  rejection_reason: string | null
  proof_revision: number
}

export interface ProofVersion {
  revision: number
  filename: string
  size_bytes: number
  uploaded_by: string
  uploaded_at: string
  reason: string | null
}

export const reportStatus: Record<ReportStatus, string> = {
  PENDING: 'Pendiente de revisión',
  APPROVED: 'Aprobado',
  REJECTED: 'Rechazado',
}

const ownerPath = (unitId: string) => `/api/owner/properties/${encodeURIComponent(unitId)}/payment-reports`
const buildingPath = (buildingId: string) => `/api/admin/buildings/${encodeURIComponent(buildingId)}/payment-reports`

export function ownerReports(unitId: string, signal: AbortSignal) {
  return propertyRequest<PaymentReport[]>(ownerPath(unitId), { signal })
}

export function submitReport(unitId: string, data: PaymentInput, file: File) {
  return propertyRequest<PaymentReport>(ownerPath(unitId), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/octet-stream',
      'X-Edificios-Request': '1',
      'X-Edificios-Report': encodeURIComponent(JSON.stringify({ ...data, filename: file.name })),
    },
    body: file,
  }, 90_000)
}

export function buildingReports(buildingId: string, signal: AbortSignal) {
  return propertyRequest<PaymentReport[]>(buildingPath(buildingId), { signal })
}

export function proofDownload(report: PaymentReport, buildingId?: string, revision = 0) {
  const path = buildingId ? buildingPath(buildingId) : ownerPath(report.unit_id)
  return `${path}/${encodeURIComponent(report.id)}/proof?revision=${revision}`
}

export function approveReport(buildingId: string, reportId: string, values: PaymentValues & { proof_revision: number }) {
  return writeProperty<PaymentReport>(`${buildingPath(buildingId)}/${encodeURIComponent(reportId)}/approval`, 'PUT', values)
}

export function rejectReport(buildingId: string, reportId: string, reason: string, proofRevision: number) {
  return writeProperty<PaymentReport>(`${buildingPath(buildingId)}/${encodeURIComponent(reportId)}/rejection`, 'PUT', { reason, proof_revision: proofRevision })
}

export function proofHistory(report: PaymentReport, signal: AbortSignal, buildingId?: string) {
  const path = buildingId ? buildingPath(buildingId) : ownerPath(report.unit_id)
  return propertyRequest<ProofVersion[]>(`${path}/${encodeURIComponent(report.id)}/proofs`, { signal })
}

export function replaceProof(
  buildingId: string,
  report: PaymentReport,
  requestId: string,
  reason: string,
  file: File,
) {
  const data = { request_id: requestId, proof_revision: report.proof_revision, reason, filename: file.name }
  return propertyRequest<PaymentReport>(`${buildingPath(buildingId)}/${encodeURIComponent(report.id)}/proofs`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/octet-stream',
      'X-Edificios-Request': '1',
      'X-Edificios-Report': encodeURIComponent(JSON.stringify(data)),
    },
    body: file,
  }, 90_000)
}
