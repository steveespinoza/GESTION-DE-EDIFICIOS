import { propertyRequest, writeProperty } from '../properties/api'

export interface InvoiceInput {
  category_id: string
  billing_year: number
  billing_month: number
  start_date: string
  end_date: string
  total_amount: string
}

interface InvoiceSummary extends InvoiceInput {
  id: string
  category_name: string
}

interface InvoiceDetail extends InvoiceSummary {
  charges: { unit_id: string; unit_number: string; amount: string }[]
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
