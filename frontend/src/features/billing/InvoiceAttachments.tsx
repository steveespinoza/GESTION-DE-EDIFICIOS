import { useCallback, useState, type FormEvent } from 'react'
import { useOutletContext } from 'react-router-dom'

import { PropertyRequestError } from '../properties/api'
import { usePropertyQuery } from '../properties/usePropertyQuery'
import { attachmentDownload, listAttachments, uploadAttachment, type AttachmentKind } from './attachmentApi'

const maxFileBytes = 10 * 1024 * 1024
const accepted = '.pdf,.png,.jpg,.jpeg'

function uploadError(error: unknown) {
  if (error instanceof PropertyRequestError && error.detail) return error.detail
  return 'No se pudo confirmar la carga. Revisa los archivos antes de volver a intentarlo.'
}

export function InvoiceAttachments({ buildingId, invoiceId }: { buildingId: string; invoiceId: string }) {
  const onSessionEnded = useOutletContext<() => void>()
  const load = useCallback((signal: AbortSignal) => listAttachments(buildingId, invoiceId, signal), [buildingId, invoiceId])
  const { query, retry } = usePropertyQuery(load)
  const [busy, setBusy] = useState(false)
  const [errors, setErrors] = useState<string[]>([])
  const voucher = query.status === 'ready' && query.data.some((file) => file.kind === 'VOUCHER')

  async function saveFiles(event: FormEvent<HTMLFormElement>, kind: AttachmentKind) {
    event.preventDefault()
    const form = event.currentTarget
    const files = new FormData(form).getAll('files').filter((value): value is File => value instanceof File && Boolean(value.name))
    let uploaded = false
    const failures: string[] = []
    setBusy(true)
    setErrors([])
    try {
      for (const file of files) {
        if (file.size > maxFileBytes) {
          failures.push(`${file.name} supera el límite de 10 MiB.`)
          continue
        }
        try {
          await uploadAttachment(buildingId, invoiceId, kind, file)
          uploaded = true
        } catch (error) {
          if (error instanceof PropertyRequestError && error.status === 401) {
            onSessionEnded()
            return
          }
          failures.push(`${file.name}. ${uploadError(error)}`)
        }
      }
      setErrors(failures)
      if (uploaded) {
        form.reset()
        retry()
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="building-surface invoice-attachments" aria-labelledby="attachment-title">
      <h2 id="attachment-title">Archivos del proveedor</h2>
      {query.status === 'loading' && <p role="status">Cargando archivos…</p>}
      {query.status === 'error' && (
        <div>
          <p role="alert">No se pudieron cargar los archivos.</p>
          <button type="button" onClick={retry}>Volver a intentar</button>
        </div>
      )}
      {query.status === 'ready' && (
        <>
          {query.data.length === 0 ? <p>Esta factura todavía no tiene archivos.</p> : (
            <ul>
              {query.data.map((file) => (
                <li key={file.id}>
                  <a href={attachmentDownload(buildingId, invoiceId, file.id)} referrerPolicy="no-referrer">
                    {file.kind === 'VOUCHER' ? 'Comprobante · ' : ''}{file.filename}
                  </a>
                </li>
              ))}
            </ul>
          )}
          <p id="attachment-format">PDF, PNG o JPEG. Hasta 10 MiB por archivo.</p>
          <div className="building-grid invoice-attachment-forms">
            <form className="building-form" onSubmit={(event) => void saveFiles(event, 'DOCUMENT')} aria-busy={busy}>
              <label>
                Adjuntos de la factura
                <input type="file" name="files" accept={accepted} multiple required disabled={busy} aria-describedby="attachment-format" />
              </label>
              <button type="submit" disabled={busy}>Subir adjuntos</button>
            </form>
            {!voucher && (
              <form className="building-form" onSubmit={(event) => void saveFiles(event, 'VOUCHER')} aria-busy={busy}>
                <label>
                  Comprobante de pago al proveedor
                  <input type="file" name="files" accept={accepted} required disabled={busy} aria-describedby="attachment-format" />
                </label>
                <button type="submit" disabled={busy}>Subir comprobante</button>
              </form>
            )}
          </div>
        </>
      )}
      {busy && <p role="status">Subiendo archivos…</p>}
      {errors.length > 0 && <ul className="form-error" role="alert">{errors.map((error, index) => <li key={index}>{error}</li>)}</ul>}
    </section>
  )
}
