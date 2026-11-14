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

export class BuildingRequestError extends Error {
  constructor(public readonly status: number) {
    super(`HTTP ${status}`)
  }
}

async function request<T>(endpoint: string, options: RequestInit): Promise<T> {
  const timeout = AbortSignal.timeout(10_000)
  const signal = options.signal ? AbortSignal.any([options.signal, timeout]) : timeout
  const response = await fetch(endpoint, { ...options, signal })
  if (!response.ok) throw new BuildingRequestError(response.status)
  return response.json()
}

export function listBuildings(signal: AbortSignal) {
  return request<BuildingSummary[]>(buildingsEndpoint, { signal })
}

export function readBuilding(id: string, signal: AbortSignal) {
  return request<Building>(`${buildingsEndpoint}/${encodeURIComponent(id)}`, { signal })
}

export function saveBuilding(building: BuildingInput, id?: string) {
  const endpoint = id ? `${buildingsEndpoint}/${encodeURIComponent(id)}` : buildingsEndpoint
  return request<Building>(endpoint, {
    method: id ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Edificios-Request': '1' },
    body: JSON.stringify(building),
  })
}

export function buildingErrorMessage(error: unknown, fallback: string) {
  if (error instanceof BuildingRequestError) {
    if (error.status === 403) return 'Tu cuenta no tiene acceso a esta sección.'
    if (error.status === 404) return 'No se encontró el edificio.'
    if (error.status === 422) return 'Revisa el nombre, la capacidad y los datos de contacto.'
  }
  return fallback
}
