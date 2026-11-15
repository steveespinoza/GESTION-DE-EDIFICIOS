import { propertyRequest } from '../properties/api'

export type AttachmentKind = 'DOCUMENT' | 'VOUCHER'

interface InvoiceAttachment {
  id: string
  kind: AttachmentKind
  filename: string
  content_type: string
  size_bytes: number
  uploaded_at: string
}

const endpoint = (buildingId: string, invoiceId: string) =>
  `/api/admin/buildings/${encodeURIComponent(buildingId)}/invoices/${encodeURIComponent(invoiceId)}/attachments`

export function listAttachments(buildingId: string, invoiceId: string, signal: AbortSignal) {
  return propertyRequest<InvoiceAttachment[]>(endpoint(buildingId, invoiceId), { signal })
}

export function uploadAttachment(buildingId: string, invoiceId: string, kind: AttachmentKind, file: File) {
  const params = new URLSearchParams({ kind, filename: file.name })
  return propertyRequest<InvoiceAttachment>(`${endpoint(buildingId, invoiceId)}?${params}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/octet-stream', 'X-Edificios-Request': '1' },
    body: file,
  }, 90_000)
}

export function attachmentDownload(buildingId: string, invoiceId: string, attachmentId: string) {
  return `${endpoint(buildingId, invoiceId)}/${encodeURIComponent(attachmentId)}/download`
}
