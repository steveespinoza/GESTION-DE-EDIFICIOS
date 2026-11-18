import { propertyRequest } from '../properties/api'
import type { Period } from './api'

export interface Receipt extends Period {
  id: string
  version: number
  issued_at: string
  issued_by: string
  reason: string
  due_date: string | null
  total_pending: string
  credit: string
  size_bytes: number
  sha256: string
}

const endpoint = (unitId: string, buildingId?: string) => buildingId
  ? `/api/admin/buildings/${encodeURIComponent(buildingId)}/units/${encodeURIComponent(unitId)}/receipts`
  : `/api/owner/properties/${encodeURIComponent(unitId)}/receipts`

export function listReceipts(unitId: string, buildingId: string | undefined, signal: AbortSignal) {
  return propertyRequest<Receipt[]>(endpoint(unitId, buildingId), { signal })
}

export function issueReceipt(unitId: string, buildingId: string, input: Period & { revision: number; request_id: string; reason: string }) {
  return propertyRequest<Receipt>(endpoint(unitId, buildingId), {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Edificios-Request': '1' }, body: JSON.stringify(input),
  }, 30_000)
}

export function receiptDownload(unitId: string, buildingId: string | undefined, receiptId: string) {
  return `${endpoint(unitId, buildingId)}/${encodeURIComponent(receiptId)}/pdf`
}
