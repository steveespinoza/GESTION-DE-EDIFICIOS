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

export function proofDownload(report: PaymentReport, buildingId?: string) {
  const path = buildingId ? buildingPath(buildingId) : ownerPath(report.unit_id)
  return `${path}/${encodeURIComponent(report.id)}/proof`
}

export function approveReport(buildingId: string, reportId: string, values: PaymentValues) {
  return writeProperty<PaymentReport>(`${buildingPath(buildingId)}/${encodeURIComponent(reportId)}/approval`, 'PUT', values)
}

export function rejectReport(buildingId: string, reportId: string, reason: string) {
  return writeProperty<PaymentReport>(`${buildingPath(buildingId)}/${encodeURIComponent(reportId)}/rejection`, 'PUT', { reason })
}
