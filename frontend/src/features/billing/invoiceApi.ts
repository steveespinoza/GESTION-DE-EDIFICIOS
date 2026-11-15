import { propertyRequest, writeProperty } from '../properties/api'

export interface InvoiceValues {
  start_date: string
  end_date: string
  total_amount: string
  total_volume?: string
  readings?: MeterReadingInput[]
}

export interface InvoiceInput extends InvoiceValues {
  category_id: string
  billing_year: number
  billing_month: number
}

export interface CorrectionInput extends InvoiceValues {
  revision: number
  reason: string
}

interface MeterReadingInput {
  unit_id: string
  previous_reading: string
  current_reading: string
  rollover_confirmed: boolean
}

export interface MeterReadingDefaults {
  unit_id: string
  unit_number: string
  previous_reading: string | null
}

interface InvoiceSummary extends Omit<InvoiceInput, 'total_volume' | 'readings'> {
  id: string
  category_name: string
}

export interface InvoiceDetail extends InvoiceSummary {
  total_volume?: string
  common_volume?: string
  revision: number
  accounting_locked: boolean
  corrections: { revision: number; reason: string; corrected_by: string; corrected_at: string }[]
  charges: {
    unit_id: string
    unit_number: string
    amount: string
    meter?: Omit<MeterReadingInput, 'unit_id' | 'rollover_confirmed'> & {
      consumption: string
      own_amount: string
      common_amount: string
      rolled_over: boolean
    }
  }[]
}

export const invoicePath = (buildingId: string) => `/admin/edificios/${buildingId}/facturas`
const endpoint = (buildingId: string) => `/api/admin/buildings/${encodeURIComponent(buildingId)}/invoices`

export function listInvoices(buildingId: string, signal: AbortSignal) {
  return propertyRequest<InvoiceSummary[]>(endpoint(buildingId), { signal })
}

export function readInvoice(buildingId: string, invoiceId: string, signal: AbortSignal) {
  return propertyRequest<InvoiceDetail>(`${endpoint(buildingId)}/${encodeURIComponent(invoiceId)}`, { signal })
}

export function createInvoice(buildingId: string, input: InvoiceInput) {
  return writeProperty<InvoiceDetail>(endpoint(buildingId), 'POST', input)
}

export function correctInvoice(buildingId: string, invoiceId: string, input: CorrectionInput) {
  return writeProperty<InvoiceDetail>(`${endpoint(buildingId)}/${encodeURIComponent(invoiceId)}`, 'PUT', input)
}

export function readMeterDefaults(
  buildingId: string,
  categoryId: string,
  year: string,
  month: string,
  signal: AbortSignal,
) {
  const params = new URLSearchParams({ category_id: categoryId, billing_year: year, billing_month: month })
  return propertyRequest<MeterReadingDefaults[]>(`${endpoint(buildingId)}/meter-readings?${params}`, { signal })
}
