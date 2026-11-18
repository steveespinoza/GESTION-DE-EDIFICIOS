from uuid import UUID

from sqlalchemy.orm import Session

from app.billing.allocation import split_linear
from app.billing.errors import InvoiceConflict, InvoiceNotFound
from app.billing.invoice_schemas import (
    InvoiceDetail,
    LinearInvoiceCorrection,
    MeteredInvoiceCorrection,
)
from app.billing.invoices import (
    correction_history,
    invoice_detail,
    invoice_records,
    scoped_invoice,
)
from app.billing.metering import metered_records, to_milli
from app.billing.models import InvoiceCorrection
from app.collections.ledger import settle_building
from app.properties.service import lock_building


def correct_invoice(
    db: Session,
    building_id: UUID,
    invoice_id: UUID,
    data: LinearInvoiceCorrection | MeteredInvoiceCorrection,
    corrected_by: UUID,
) -> InvoiceDetail:
    # Issuing another invoice can establish the next reading for this correction.
    if lock_building(db, building_id) is None:
        raise InvoiceNotFound("Factura no encontrada.")
    invoice, category_name = scoped_invoice(db, building_id, invoice_id, read=False)
    if invoice.accounting_locked_at is not None:
        raise InvoiceConflict(
            "La factura tiene movimientos contables. La diferencia requiere un ajuste."
        )
    if invoice.revision != data.revision:
        raise InvoiceConflict(
            "La factura cambió desde que la abriste. Recarga la ficha antes de corregirla."
        )
    if isinstance(data, MeteredInvoiceCorrection) != (
        invoice.total_volume_milli is not None
    ):
        raise InvoiceConflict(
            "La corrección debe coincidir con el tipo de reparto de la factura."
        )

    charges, readings = invoice_records(db, invoice)
    before = invoice_detail(invoice, category_name, charges, readings)
    total_cents = int(data.total_amount.scaleb(2))
    if isinstance(data, MeteredInvoiceCorrection):
        units = [(charge.unit_id, charge.unit_number) for charge in charges]
        new_charges, new_readings = metered_records(
            db, invoice, units, data, total_cents=total_cents
        )
        by_unit = {reading.unit_id: reading for reading in new_readings}
        for reading in readings:
            new = by_unit[reading.unit_id]
            reading.previous_milli = new.previous_milli
            reading.current_milli = new.current_milli
            reading.consumption_milli = new.consumption_milli
        for charge, new_charge in zip(charges, new_charges, strict=True):
            charge.amount_cents = new_charge.amount_cents
            charge.common_cents = new_charge.common_cents
        invoice.total_volume_milli = to_milli(data.total_volume)
    else:
        amounts = split_linear(total_cents, len(charges))
        for charge, amount in zip(charges, amounts, strict=True):
            charge.amount_cents = amount
    invoice.total_cents = total_cents
    invoice.start_date = data.start_date
    invoice.end_date = data.end_date

    settle_building(db, building_id, corrected_by)
    after = invoice_detail(invoice, category_name, charges, readings)
    if after != before:
        invoice.revision += 1
        after.revision = invoice.revision
        db.add(
            InvoiceCorrection(
                invoice_id=invoice.id,
                revision=invoice.revision,
                reason=data.reason,
                corrected_by_id=corrected_by,
                before=before.model_dump(mode="json", exclude={"corrections"}),
                after=after.model_dump(mode="json", exclude={"corrections"}),
            )
        )
    after.corrections = correction_history(db, invoice.id)
    db.commit()
    return after
