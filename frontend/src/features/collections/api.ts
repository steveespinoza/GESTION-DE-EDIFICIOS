import { propertyRequest, writeProperty } from '../properties/api'
import type { ChargeAdjustment } from '../billing/invoiceApi'

export interface Period {
  billing_year: number
  billing_month: number
}

interface Charge extends Period {
  id: string
  service: string
  coverage_end: string
  amount: string
  original_amount: string
  adjustment: string
  applied: string
  balance: string
  consumption: string | null
  due_date: string | null
  overdue: boolean
}

export interface Payment extends Period {
  id: string
  received_on: string
  amount: string
  credit: string
  reference: string | null
  applications: (Period & {
    id: string; charge_id: string; service: string; amount: string; released: string; net_amount: string
    applied_at: string; applied_by: string | null; automatic: boolean
  })[]
}

export interface CarryForward extends Period {
  charge_id: string
  source_year: number
  source_month: number
  service: string
  amount: string
  balance: string
  recorded_at: string
  recorded_by: string | null
}

export interface Statement {
  building_name: string
  unit_number: string
  balance: string
  credit: string
  charges: Charge[]
  as_of: string
  overdue_balance: string
  payments: Payment[]
  carry_forwards: CarryForward[]
  adjustments: ChargeAdjustment[]
}

export type PaymentValues = Pick<Payment, 'received_on' | 'amount' | 'reference'>

export interface PaymentInput extends Period, PaymentValues {
  request_id: string
}

const adminUnit = (buildingId: string, unitId: string) => `/api/admin/buildings/${encodeURIComponent(buildingId)}/units/${encodeURIComponent(unitId)}`

export function readStatement(unitId: string, buildingId: string | undefined, signal: AbortSignal) {
  const scope = buildingId ? adminUnit(buildingId, unitId) : `/api/owner/properties/${encodeURIComponent(unitId)}`
  return propertyRequest<Statement>(`${scope}/statement`, { signal })
}

export function registerPayment(buildingId: string, unitId: string, payment: PaymentInput) {
  return writeProperty<Payment>(`${adminUnit(buildingId, unitId)}/payments`, 'POST', payment)
}
