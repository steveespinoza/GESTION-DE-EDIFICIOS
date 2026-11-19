import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, Navigate, useOutletContext, useParams } from 'react-router-dom'

import { PropertyRequestError, readBuilding } from '../properties/api'
import { usePropertyQuery } from '../properties/usePropertyQuery'
import { issueBatchItem, listBatches, readBatch, type Batch, type BatchSummary } from './batchApi'
import { ReceiptBatchForm } from './ReceiptBatchForm'
import { receiptDownload } from './receiptApi'
import { money, periodLabel } from './format'
import './collections.css'

const statusLabel = { PENDING: 'Pendiente', ISSUED: 'Emitido', FAILED: 'Falló', SKIPPED: 'Sin cargos del periodo' }

function BatchWorkspace({ buildingId, name, initialHistory }: { buildingId: string; name: string; initialHistory: BatchSummary[] }) {
  const endSession = useOutletContext<() => void>()
  const [history, setHistory] = useState(initialHistory)
  const [batch, setBatch] = useState<Batch>()
  const [showForm, setShowForm] = useState(initialHistory.length === 0)
  const [formKey, setFormKey] = useState(0)
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const active = useRef(false)
  const mounted = useRef(true)
  const stop = useRef(false)
  const controller = useRef<AbortController | null>(null)
  const feedback = useRef<HTMLParagraphElement>(null)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; controller.current?.abort() } }, [])
  useEffect(() => { if (notice || error) feedback.current?.focus() }, [notice, error])

  function remember(value: Batch) {
    setBatch(value)
    setHistory((previous) => [value, ...previous.filter((item) => item.id !== value.id)].sort((a, b) => b.created_at.localeCompare(a.created_at)))
  }

  function start() {
    active.current = true
    stop.current = false
    setBusy(true)
    setNotice('')
    setError('')
    controller.current = new AbortController()
    return controller.current
  }

  function finish() {
    active.current = false
    setBusy(false)
    setProgress('')
  }

  async function process(value: Batch, unitIds?: string[]) {
    if (active.current || !mounted.current) return
    const abort = start()
    remember(value)
    setShowForm(false)
    const targets = value.items.filter((item) => unitIds ? unitIds.includes(item.unit_id) : item.status === 'PENDING' || item.retryable)
    let current = value
    try {
      for (const [index, item] of targets.entries()) {
        if (stop.current) break
        setProgress(`Procesando unidad ${item.unit_number} (${index + 1} de ${targets.length})…`)
        current = await issueBatchItem(buildingId, value.id, item.unit_id, abort.signal)
        remember(current)
      }
      setNotice(`${stop.current ? 'Proceso detenido después de la unidad actual.' : 'Procesamiento finalizado.'} Emitidos: ${current.issued}. Fallos: ${current.failed}. Pendientes: ${current.pending}. Omitidos: ${current.skipped}. El lote quedó guardado.`)
    } catch (issue) {
      if (abort.signal.aborted) return
      if (issue instanceof PropertyRequestError && issue.status === 401) endSession()
      else setError('No se pudo confirmar la última unidad. Actualiza el lote para comprobar el resultado antes de continuar. Los recibos confirmados se conservan.')
    } finally { if (!abort.signal.aborted) finish() }
  }

  async function openBatch(id: string) {
    if (active.current) return
    const abort = start()
    try {
      remember(await readBatch(buildingId, id, abort.signal))
      setShowForm(false)
      setNotice('Lote actualizado. Puedes continuar los pendientes o reintentar los fallos recuperables.')
    } catch (issue) {
      if (abort.signal.aborted) return
      if (issue instanceof PropertyRequestError && issue.status === 401) endSession()
      else setError('No se pudo consultar el lote. Vuelve a intentar.')
    } finally { if (!abort.signal.aborted) finish() }
  }

  async function refreshHistory() {
    if (active.current) return
    const abort = start()
    try { setHistory(await listBatches(buildingId, abort.signal)); setNotice('Historial actualizado.') }
    catch (issue) {
      if (abort.signal.aborted) return
      if (issue instanceof PropertyRequestError && issue.status === 401) endSession()
      else setError('No se pudo actualizar el historial.')
    } finally { if (!abort.signal.aborted) finish() }
  }

  return <section className="building-page unit-statement" aria-labelledby="receipt-batches-title">
    <Link to={`/admin/edificios/${buildingId}/cobranzas`}>Volver a Cobranzas</Link>
    <h1 id="receipt-batches-title">Recibos por lote · {name}</h1>
    <p>El progreso se guarda por unidad. Si cierras esta página, abre el lote desde el historial para consultar lo emitido y continuar. Cada PDF conserva los datos de su momento de emisión.</p>
    <div className="building-form-actions"><button type="button" disabled={busy} onClick={() => { setFormKey((key) => key + 1); setShowForm(true); setNotice(''); setError('') }}>Preparar nuevo lote</button><button type="button" disabled={busy} onClick={refreshHistory}>Actualizar historial</button></div>
    {progress && <p role="status">{progress}</p>}
    {(notice || error) && <p ref={feedback} tabIndex={-1} role={error ? 'alert' : 'status'}>{error || notice}</p>}
    {showForm && <ReceiptBatchForm key={formKey} buildingId={buildingId} onPreparing={setBusy} disabled={busy} onPrepared={async (value) => { if (!mounted.current) return; remember(value); await process(value) }} />}
    {batch && !showForm && <section className="building-surface" aria-labelledby="active-batch-title" aria-busy={busy}>
      <h2 id="active-batch-title">Lote de {periodLabel(batch)}</h2>
      <p>Vencimiento {batch.due_date} · {batch.reason}</p>
      <p>Preparado por {batch.created_by} · <time dateTime={batch.created_at}>{new Date(batch.created_at).toLocaleString('es-PE')}</time></p>
      <p>Emitidos: {batch.issued} · Fallos: {batch.failed} · Pendientes: {batch.pending} · Omitidos: {batch.skipped}</p>
      <div className="building-form-actions">
        <button type="button" disabled={busy} onClick={() => openBatch(batch.id)}>Actualizar lote</button>
        {batch.pending > 0 && <button type="button" disabled={busy} onClick={() => process(batch, batch.items.filter((item) => item.status === 'PENDING').map((item) => item.unit_id))}>Continuar pendientes</button>}
        {batch.items.some((item) => item.retryable) && <button type="button" disabled={busy} onClick={() => process(batch, batch.items.filter((item) => item.retryable).map((item) => item.unit_id))}>Reintentar fallos</button>}
        {busy && progress && <button type="button" onClick={() => { stop.current = true }}>Detener después de esta unidad</button>}
      </div>
      <ul className="building-details receipt-history">{batch.items.map((item) => <li key={item.unit_id}>
        <h3>Unidad {item.unit_number} · {statusLabel[item.status]}</h3>
        {item.receipt && <><a href={receiptDownload(item.unit_id, buildingId, item.receipt.id)} target="_blank" rel="noreferrer">Descargar PDF de la unidad {item.unit_number} · Versión {item.receipt.version}</a><p>Pendiente al emitir: {money(item.receipt.total_pending)} · Vencimiento: {item.receipt.due_date ?? 'Sin vencimiento'}</p></>}
        {item.error_message && <p>{item.error_message}</p>}
        {item.status === 'FAILED' && !item.retryable && <p>Este lote no puede resolver el cambio. Actualiza los datos y prepara otro lote si corresponde.</p>}
        {item.attempts > 0 && <p>Intentos: {item.attempts} · Último responsable: {item.last_attempt_by ?? 'Sistema'}{item.last_attempt_at && <> · <time dateTime={item.last_attempt_at}>{new Date(item.last_attempt_at).toLocaleString('es-PE')}</time></>}</p>}
        {item.retryable && <button type="button" disabled={busy} onClick={() => process(batch, [item.unit_id])}>Reintentar unidad {item.unit_number}</button>}
      </li>)}</ul>
    </section>}
    <section className="building-surface" aria-labelledby="batch-history-title"><h2 id="batch-history-title">Historial de lotes</h2>
      {history.length === 0 ? <p>Todavía no hay lotes preparados.</p> : <ul className="building-details receipt-history">{history.map((item) => <li key={item.id}>
        <button type="button" disabled={busy} onClick={() => openBatch(item.id)}>Ver lote de {periodLabel(item)} · {new Date(item.created_at).toLocaleString('es-PE')}</button>
        <p>{item.reason} · Emitidos {item.issued} · Fallos {item.failed} · Pendientes {item.pending} · Omitidos {item.skipped}</p>
      </li>)}</ul>}
    </section>
  </section>
}

function BatchesRecord({ buildingId }: { buildingId: string }) {
  const load = useCallback(async (signal: AbortSignal) => {
    const [building, history] = await Promise.all([readBuilding(buildingId, signal), listBatches(buildingId, signal)])
    return { building, history }
  }, [buildingId])
  const { query, retry } = usePropertyQuery(load)
  if (query.status === 'loading') return <p role="status">Cargando lotes…</p>
  if (query.status === 'error') return <div><p role="alert">{query.error instanceof PropertyRequestError && query.error.status === 404 ? 'No se encontró el edificio.' : 'No se pudieron cargar los lotes.'}</p><button type="button" onClick={retry}>Volver a intentar</button></div>
  return <BatchWorkspace buildingId={buildingId} name={query.data.building.name} initialHistory={query.data.history} />
}

export function ReceiptBatchesPage() {
  const { buildingId } = useParams()
  return buildingId ? <BatchesRecord key={buildingId} buildingId={buildingId} /> : <Navigate to="/admin" replace />
}
