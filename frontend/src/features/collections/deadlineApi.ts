import { propertyRequest, writeProperty } from '../properties/api'
import type { Period } from './api'

export interface Deadline extends Period {
  id: string
  revision: number
  due_date: string
  reason: string
  recorded_by: string
  recorded_at: string
}

export interface CollectionRow extends Period {
  unit_id: string
  unit_number: string
  owner_name: string
  amount: string
  applied: string
  balance: string
  overdue_balance: string
  due_date: string | null
}

export interface CollectionOverview {
  building_name: string
  as_of: string
  balance: string
  overdue_balance: string
  rows: CollectionRow[]
  deadlines: Deadline[]
}

export function readCollections(buildingId: string, signal: AbortSignal) {
  return propertyRequest<CollectionOverview>(`/api/admin/buildings/${encodeURIComponent(buildingId)}/collections`, { signal })
}

export function saveDeadline(buildingId: string, input: Period & { request_id: string; revision: number; due_date: string; reason: string }) {
  return writeProperty<Deadline>(`/api/admin/buildings/${encodeURIComponent(buildingId)}/collection-deadlines`, 'POST', input)
}
