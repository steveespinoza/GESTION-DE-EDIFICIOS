import { propertyRequest, writeProperty } from '../properties/api'

export type CalculationType = 'LINEAR' | 'METERED'

interface ServiceCategoryInput {
  name: string
  calculation_type: CalculationType
}

interface ServiceCategory extends ServiceCategoryInput {
  id: string
  building_id: string
}

const endpoint = (buildingId: string) => `/api/admin/buildings/${encodeURIComponent(buildingId)}/services`

export function listServices(buildingId: string, signal: AbortSignal) {
  return propertyRequest<ServiceCategory[]>(endpoint(buildingId), { signal })
}

export function createService(buildingId: string, data: ServiceCategoryInput) {
  return writeProperty<ServiceCategory>(endpoint(buildingId), 'POST', data)
}
