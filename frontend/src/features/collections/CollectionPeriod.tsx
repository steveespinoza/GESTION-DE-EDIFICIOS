import { useState } from 'react'
import { Link } from 'react-router-dom'

import type { CollectionRow } from './deadlineApi'
import { money, periodLabel } from './format'

export function CollectionPeriod({ buildingId, rows, initialOpen }: { buildingId: string; rows: CollectionRow[]; initialOpen: boolean }) {
  const [open, setOpen] = useState(initialOpen)
  const title = periodLabel(rows[0])
  return <details className="collection-period" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary><span className="period-title">{title}<span>{rows.length} {rows.length === 1 ? 'unidad' : 'unidades'}</span></span><span className="period-deadline">{rows[0].due_date ? `Fecha límite: ${rows[0].due_date}` : 'Sin vencimiento'}</span></summary>
    <div className="table-scroll" role="region" aria-label={`Cobranzas de ${title}`} tabIndex={0}>
      <table className="workspace-table collections-table"><thead><tr><th scope="col">Unidad</th><th scope="col">Propietario</th><th scope="col" className="amount">Importe</th><th scope="col" className="amount">Aplicado</th><th scope="col" className="amount">Pendiente</th><th scope="col" className="amount">Vencido</th><th scope="col">Estado</th><th scope="col">Acciones</th></tr></thead><tbody>
        {rows.map((row) => <tr key={row.unit_id}>
          <th scope="row">{row.unit_number}</th><td>{row.owner_name}</td><td className="amount">{money(row.amount)}</td><td className="amount">{money(row.applied)}</td><td className="amount pending-amount">{money(row.balance)}</td><td className="amount">{money(row.overdue_balance)}</td>
          <td><span className="status-badge" data-tone={row.balance === '0.00' ? 'paid' : row.overdue_balance !== '0.00' ? 'overdue' : 'pending'}>{row.balance === '0.00' ? 'Pagado' : row.overdue_balance !== '0.00' ? 'Vencido' : row.due_date ? 'Por vencer' : 'Sin vencimiento'}</span></td>
          <td><Link to={`/admin/edificios/${buildingId}/unidades/${row.unit_id}/estado-de-cuenta`} aria-label={`Estado de cuenta de la unidad ${row.unit_number}, ${title}`}>Estado de cuenta</Link></td>
        </tr>)}
      </tbody></table>
    </div>
  </details>
}
