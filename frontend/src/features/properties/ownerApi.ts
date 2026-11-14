import { propertyRequest } from './api'

interface OwnerUnit {
  id: string
  number: string
  area_sqm: string
}

interface OwnerBuilding {
  id: string
  name: string
  address: string | null
}

interface OwnerBuildingGroup extends OwnerBuilding {
  units: OwnerUnit[]
}

interface OwnerUnitDetail extends OwnerUnit {
  building: OwnerBuilding
  payment_instructions: {
    bank_name: string | null
    account_number: string | null
    cci: string | null
    account_holder: string | null
    contact_email: string | null
  }
}

const endpoint = '/api/owner/properties'

export function listMyProperties(signal: AbortSignal) {
  return propertyRequest<OwnerBuildingGroup[]>(endpoint, { signal })
}

export function readMyUnit(unitId: string, signal: AbortSignal) {
  return propertyRequest<OwnerUnitDetail>(`${endpoint}/${encodeURIComponent(unitId)}`, { signal })
}
