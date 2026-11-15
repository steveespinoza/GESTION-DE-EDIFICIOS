from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.billing.allocation import split_metered
from app.billing.errors import InvoiceConflict
from app.billing.invoice_schemas import (
    METER_LIMIT_MILLI,
    AccountingPeriod,
    MeteredValues,
)
from app.billing.models import MeterReading, ServiceInvoice, UnitCharge


def to_milli(volume: Decimal) -> int:
    return int(volume.scaleb(3))


def from_milli(volume: int) -> Decimal:
    return Decimal(volume).scaleb(-3)


def neighboring_readings(
    db: Session, category_id: UUID, period: AccountingPeriod, *, before: bool = True
) -> dict[UUID, int]:
    invoice_period = tuple_(ServiceInvoice.billing_year, ServiceInvoice.billing_month)
    requested_period = tuple_(period.billing_year, period.billing_month)
    if before:
        value = MeterReading.current_milli
        matches = invoice_period < requested_period
        order = (
            ServiceInvoice.billing_year.desc(),
            ServiceInvoice.billing_month.desc(),
        )
    else:
        value = MeterReading.previous_milli
        matches = invoice_period > requested_period
        order = (ServiceInvoice.billing_year.asc(), ServiceInvoice.billing_month.asc())

    rows = db.execute(
        select(MeterReading.unit_id, value)
        .join(ServiceInvoice, ServiceInvoice.id == MeterReading.invoice_id)
        .where(ServiceInvoice.category_id == category_id, matches)
        .order_by(*order)
    )
    result: dict[UUID, int] = {}
    for unit_id, reading in rows:
        result.setdefault(unit_id, reading)
    return result


def metered_records(
    db: Session,
    invoice: ServiceInvoice,
    units: list[tuple[UUID, str]],
    data: MeteredValues,
    *,
    total_cents: int,
) -> tuple[list[UnitCharge], list[MeterReading]]:
    inputs = {item.unit_id: item for item in data.readings}
    if len(inputs) != len(data.readings) or inputs.keys() != {
        unit_id for unit_id, _ in units
    }:
        raise InvoiceConflict(
            "Ingresa exactamente una lectura por unidad incluida en la factura."
        )

    period = AccountingPeriod(
        billing_year=invoice.billing_year, billing_month=invoice.billing_month
    )
    previous = neighboring_readings(db, invoice.category_id, period)
    following = neighboring_readings(db, invoice.category_id, period, before=False)
    readings = []
    for unit_id, number in units:
        entry = inputs[unit_id]
        baseline = to_milli(entry.previous_reading)
        current = to_milli(entry.current_reading)
        if unit_id in previous and baseline != previous[unit_id]:
            raise InvoiceConflict(
                f"La lectura anterior de la unidad {number} cambió. Actualiza las lecturas."
            )
        if unit_id in following and current != following[unit_id]:
            raise InvoiceConflict(
                f"La lectura actual de la unidad {number} debe coincidir con la lectura anterior de la siguiente factura."
            )
        rolled_over = current < baseline
        if rolled_over != entry.rollover_confirmed:
            raise InvoiceConflict(
                f"Revisa la confirmación de vuelta a cero de la unidad {number}."
            )

        readings.append(
            MeterReading(
                invoice_id=invoice.id,
                unit_id=unit_id,
                previous_milli=baseline,
                current_milli=current,
                consumption_milli=current
                - baseline
                + (METER_LIMIT_MILLI if rolled_over else 0),
            )
        )

    total_volume = to_milli(data.total_volume)
    consumptions = [reading.consumption_milli for reading in readings]
    if sum(consumptions) > total_volume:
        raise InvoiceConflict(
            "La suma de consumos individuales supera el volumen de la factura."
        )

    shares = split_metered(total_cents, total_volume, consumptions)
    charges = [
        UnitCharge(
            invoice_id=invoice.id,
            unit_id=unit_id,
            unit_number=number,
            amount_cents=own + common,
            common_cents=common,
        )
        for (unit_id, number), (own, common) in zip(units, shares, strict=True)
    ]
    return charges, readings
