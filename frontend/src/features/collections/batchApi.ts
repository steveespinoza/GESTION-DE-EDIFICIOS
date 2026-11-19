import { propertyRequest } from '../properties/api'
import type { Period } from './api'
import type { Receipt } from './receiptApi'

export interface BatchItem {
  unit_id: string
  unit_number: string
  revision: number
  status: 'PENDING' | 'ISSUED' | 'FAILED' | 'SKIPPED'
  attempts: number
  last_attempt_at: string | null
  last_attempt_by: string | null
  error_code: string | null
  error_message: string | null
  retryable: boolean
  receipt: Receipt | null
}

export interface BatchSummary extends Period {
  id: string
  due_date: string
  deadline_revision: number
  reason: string
  created_at: string
  created_by: string
  pending: number
  issued: number
  failed: number
  skipped: number
}

export interface Batch extends BatchSummary { items: BatchItem[] }
export interface BatchInput extends Period { request_id: string; due_date: string; deadline_revision: number; reason: string }
const base = (buildingId: string) => `/api/admin/buildings/${encodeURIComponent(buildingId)}/receipt-batches`

export function listBatches(buildingId: string, signal: AbortSignal) {
  return propertyRequest<BatchSummary[]>(base(buildingId), { signal })
}

export function readBatch(buildingId: string, batchId: string, signal: AbortSignal) {
  return propertyRequest<Batch>(`${base(buildingId)}/${encodeURIComponent(batchId)}`, { signal })
}

export function prepareBatch(buildingId: string, input: BatchInput, signal: AbortSignal) {
  return propertyRequest<Batch>(base(buildingId), {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Edificios-Request': '1' }, body: JSON.stringify(input), signal,
  }, 30_000)
}

export function issueBatchItem(buildingId: string, batchId: string, unitId: string, signal: AbortSignal) {
  return propertyRequest<Batch>(`${base(buildingId)}/${encodeURIComponent(batchId)}/items/${encodeURIComponent(unitId)}/issue`, {
    method: 'POST', headers: { 'X-Edificios-Request': '1' }, signal,
  }, 60_000)
}
