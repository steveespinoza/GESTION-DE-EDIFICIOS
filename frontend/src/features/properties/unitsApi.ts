import { PropertyRequestError, propertyRequest, writeProperty } from './api'

export interface OwnerOption {
  id: string
  full_name: string
  username: string
}

export interface Owner extends OwnerOption {
  email: string | null
  phone: string | null
}

export type OwnerInput = Omit<Owner, 'id'>

export interface UnitInput {
  number: string
  area_sqm: string
}

type OwnerSelection =
  | { kind: 'existing'; id: string }
  | ({ kind: 'new'; password: string } & OwnerInput)

export interface Unit extends UnitInput {
  id: string
  building_id: string
  owner: Owner
}

export const unitsPath = (buildingId: string) => `/admin/edificios/${buildingId}/unidades`
const unitsEndpoint = (buildingId: string) => `/api/admin/buildings/${encodeURIComponent(buildingId)}/units`
const unitEndpoint = (buildingId: string, unitId: string) => `${unitsEndpoint(buildingId)}/${encodeURIComponent(unitId)}`

export function listUnits(buildingId: string, query: string, signal: AbortSignal) {
  const search = new URLSearchParams({ q: query })
  return propertyRequest<Unit[]>(`${unitsEndpoint(buildingId)}?${search}`, { signal })
}

export function readUnit(buildingId: string, unitId: string, signal: AbortSignal) {
  return propertyRequest<Unit>(unitEndpoint(buildingId, unitId), { signal })
}

export function listOwners(signal: AbortSignal) {
  return propertyRequest<OwnerOption[]>('/api/admin/owners', { signal })
}

export function createUnit(buildingId: string, input: UnitInput, owner: OwnerSelection) {
  return writeProperty<Unit>(unitsEndpoint(buildingId), 'POST', { ...input, owner })
}

export function updateUnit(buildingId: string, unitId: string, input: UnitInput) {
  return writeProperty<Unit>(unitEndpoint(buildingId, unitId), 'PUT', input)
}

export function updateOwner(buildingId: string, unitId: string, input: OwnerInput) {
  return writeProperty<Owner>(`${unitEndpoint(buildingId, unitId)}/owner`, 'PUT', input)
}

export function unitErrorMessage(error: unknown, fallback: string) {
  if (error instanceof PropertyRequestError) {
    if (error.status === 403) return 'Tu cuenta no tiene acceso a esta sección.'
    if (error.status === 404) return 'No se encontró el registro solicitado.'
    if (error.status === 409 && error.detail) return error.detail
    if (error.status === 422) return 'Revisa el número, el área o los datos del propietario.'
  }
  return fallback
}
