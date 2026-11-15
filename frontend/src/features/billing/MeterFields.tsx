import { useCallback, useState } from 'react'

import { usePropertyQuery } from '../properties/usePropertyQuery'
import { readMeterDefaults, type MeterReadingDefaults } from './invoiceApi'

function ReadingFields({ meter }: { meter: MeterReadingDefaults }) {
  const [previous, setPrevious] = useState(meter.previous_reading ?? '0.000')
  const [current, setCurrent] = useState('')
  const rollover = current !== '' && previous !== '' && Number(current) < Number(previous)
  const id = meter.unit_id

  return (
    <fieldset className="building-surface">
      <legend>Unidad {meter.unit_number}</legend>
      <input type="hidden" name="meter_unit" value={id} />
      <div className="building-form-grid">
        <label>
          Lectura anterior
          <input
            type="number" min="0" max="99999.999" step="0.001" required
            name={`previous_${id}`} value={previous} readOnly={meter.previous_reading !== null}
            onChange={(event) => setPrevious(event.target.value)}
          />
        </label>
        <label>
          Lectura actual
          <input
            type="number" min="0" max="99999.999" step="0.001" required
            name={`current_${id}`} value={current}
            onChange={(event) => setCurrent(event.target.value)}
          />
        </label>
      </div>
      {rollover && (
        <label className="meter-confirmation">
          <input type="checkbox" name={`rollover_${id}`} required />
          Confirmo la vuelta a cero del contador.
        </label>
      )}
    </fieldset>
  )
}

interface MeterFieldsProps {
  buildingId: string
  categoryId: string
  year: string
  month: string
}

export function MeterFields({ buildingId, categoryId, year, month }: MeterFieldsProps) {
  const load = useCallback(
    (signal: AbortSignal) => readMeterDefaults(buildingId, categoryId, year, month, signal),
    [buildingId, categoryId, year, month],
  )
  const { query, retry } = usePropertyQuery(load)
  if (query.status === 'loading') return <p role="status">Cargando lecturas anteriores…</p>
  if (query.status === 'error') {
    return (
      <div>
        <p role="alert">No se pudieron cargar las lecturas.</p>
        <button type="button" onClick={retry}>Volver a intentar</button>
      </div>
    )
  }
  if (query.data.length === 0) return <p>Registra al menos una unidad antes de facturar.</p>

  return (
    <div className="building-form">
      <label>
        Volumen de la factura (m³)
        <input name="total_volume" type="number" min="0.001" max="999999999.999" step="0.001" required />
      </label>
      {query.data.map((meter) => <ReadingFields key={meter.unit_id} meter={meter} />)}
    </div>
  )
}
