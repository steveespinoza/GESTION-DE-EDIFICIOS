export interface BuildingSummary {
  id: string
  name: string
  address: string | null
  total_units: number
}

export interface Building extends BuildingSummary {
  bank_name: string | null
  account_number: string | null
  cci: string | null
  account_holder: string | null
  contact_email: string | null
}

export type BuildingInput = Omit<Building, 'id'>

const buildingsEndpoint = '/api/admin/buildings'

export class PropertyRequestError extends Error {
  constructor(public readonly status: number, public readonly detail?: string) {
    super(`HTTP ${status}`)
  }
}

export async function propertyRequest<T>(endpoint: string, options: RequestInit, timeoutMs = 10_000): Promise<T> {
  const timeout = AbortSignal.timeout(timeoutMs)
  const signal = options.signal ? AbortSignal.any([options.signal, timeout]) : timeout
  const response = await fetch(endpoint, { ...options, signal })
  if (!response.ok) {
    if ([409, 413, 415, 503].includes(response.status)) {
      const data: { detail?: unknown } | null = await response.json().catch(() => null)
      throw new PropertyRequestError(response.status, typeof data?.detail === 'string' ? data.detail : undefined)
    }
    throw new PropertyRequestError(response.status)
  }
  return response.json()
}

export function writeProperty<T>(endpoint: string, method: 'POST' | 'PUT', data: unknown) {
  return propertyRequest<T>(endpoint, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-Edificios-Request': '1' },
    body: JSON.stringify(data),
  })
}

export function listBuildings(signal: AbortSignal) {
  return propertyRequest<BuildingSummary[]>(buildingsEndpoint, { signal })
}

export function readBuilding(id: string, signal: AbortSignal) {
  return propertyRequest<Building>(`${buildingsEndpoint}/${encodeURIComponent(id)}`, { signal })
}

export function saveBuilding(building: BuildingInput, id?: string) {
  const endpoint = id ? `${buildingsEndpoint}/${encodeURIComponent(id)}` : buildingsEndpoint
  return writeProperty<Building>(endpoint, id ? 'PUT' : 'POST', building)
}

export function buildingErrorMessage(error: unknown, fallback: string) {
  if (error instanceof PropertyRequestError) {
    if (error.status === 403) return 'Tu cuenta no tiene acceso a esta sección.'
    if (error.status === 404) return 'No se encontró el edificio.'
    if (error.status === 422) return 'Revisa el nombre, la capacidad y los datos de contacto.'
    if (error.status === 409 && error.detail) return error.detail
  }
  return fallback
}
