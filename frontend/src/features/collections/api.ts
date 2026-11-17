import { propertyRequest, writeProperty } from '../properties/api'

export interface Period {
  billing_year: number
  billing_month: number
}

interface Charge extends Period {
  id: string
  service: string
  coverage_end: string
  amount: string
  applied: string
  balance: string
  consumption: string | null
}

export interface Payment extends Period {
  id: string
  received_on: string
  amount: string
  credit: string
  reference: string | null
  applications: (Period & { charge_id: string; service: string; amount: string })[]
}

export interface Statement {
  building_name: string
  unit_number: string
  balance: string
  credit: string
  charges: Charge[]
  payments: Payment[]
}

export type PaymentInput = Pick<Payment, 'billing_year' | 'billing_month' | 'received_on' | 'amount' | 'reference'> & { request_id: string }

const adminUnit = (buildingId: string, unitId: string) => `/api/admin/buildings/${encodeURIComponent(buildingId)}/units/${encodeURIComponent(unitId)}`

export function readStatement(unitId: string, buildingId: string | undefined, signal: AbortSignal) {
  const scope = buildingId ? adminUnit(buildingId, unitId) : `/api/owner/properties/${encodeURIComponent(unitId)}`
  return propertyRequest<Statement>(`${scope}/statement`, { signal })
}

export function registerPayment(buildingId: string, unitId: string, payment: PaymentInput) {
  return writeProperty<Payment>(`${adminUnit(buildingId, unitId)}/payments`, 'POST', payment)
}
