import { money, periodLabel } from '../collections/format'
import type { ChargeAdjustment } from './invoiceApi'

export function ChargeAdjustmentHistory({ adjustments }: { adjustments: ChargeAdjustment[] }) {
  return (
    <section className="building-surface" aria-labelledby="charge-adjustment-history-title">
      <h2 id="charge-adjustment-history-title">Historial de ajustes</h2>
      {adjustments.length === 0 ? <p>Todavía no hay ajustes registrados.</p> : (
        <dl className="building-details">
          {adjustments.map((adjustment) => (
            <div key={adjustment.id}>
              <dt>{adjustment.service} · {periodLabel(adjustment)} · Unidad {adjustment.unit_number} · Ajuste {adjustment.revision}</dt>
              <dd>De {money(adjustment.previous_amount)} a {money(adjustment.new_amount)} · Diferencia {money(adjustment.difference)}</dd>
              {adjustment.released_credit !== '0.00' && <dd>Crédito liberado {money(adjustment.released_credit)}</dd>}
              <dd>Motivo · {adjustment.reason}</dd>
              <dd>{adjustment.recorded_by} · <time dateTime={adjustment.recorded_at}>{new Date(adjustment.recorded_at).toLocaleString('es-PE')}</time></dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  )
}
