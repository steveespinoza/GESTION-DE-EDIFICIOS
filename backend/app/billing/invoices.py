from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from psycopg.errors import UniqueViolation
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billing.allocation import split_linear
from app.billing.catalog import building_exists
from app.billing.errors import InvoiceConflict, InvoiceNotFound
from app.billing.invoice_schemas import (
    AccountingPeriod,
    ChargeDetail,
    CorrectionDetail,
    InvoiceDetail,
    InvoiceSummary,
    LinearInvoiceInput,
    MeteredChargeDetail,
    MeteredInvoiceInput,
    MeterReadingDefaults,
)
from app.billing.metering import (
    from_milli,
    metered_records,
    neighboring_readings,
    to_milli,
)
from app.billing.models import (
    INVOICE_PERIOD_CONSTRAINT,
    CalculationType,
    InvoiceCorrection,
    MeterReading,
    ServiceCategory,
    ServiceInvoice,
    UnitCharge,
)
from app.identity.models import Account
from app.properties.models import Unit
from app.properties.service import lock_building


def summarize(invoice: ServiceInvoice, category_name: str) -> InvoiceSummary:
    return InvoiceSummary(
        id=invoice.id,
        category_id=invoice.category_id,
        category_name=category_name,
        billing_year=invoice.billing_year,
        billing_month=invoice.billing_month,
        start_date=invoice.start_date,
        end_date=invoice.end_date,
        total_amount=Decimal(invoice.total_cents).scaleb(-2),
    )


def invoice_detail(
    invoice: ServiceInvoice,
    category_name: str,
    charges: Sequence[UnitCharge],
    readings: Sequence[MeterReading] = (),
) -> InvoiceDetail:
    metering = {reading.unit_id: reading for reading in readings}
    volume = invoice.total_volume_milli
    return InvoiceDetail(
        **summarize(invoice, category_name).model_dump(),
        charges=[
            ChargeDetail(
                unit_id=charge.unit_id,
                unit_number=charge.unit_number,
                amount=Decimal(charge.amount_cents).scaleb(-2),
                meter=meter_detail(charge, metering.get(charge.unit_id)),
            )
            for charge in charges
        ],
        total_volume=from_milli(volume) if volume is not None else None,
        revision=invoice.revision,
        accounting_locked=invoice.accounting_locked_at is not None,
        common_volume=from_milli(
            volume - sum(reading.consumption_milli for reading in readings)
        )
        if volume is not None
        else None,
    )


def meter_detail(
    charge: UnitCharge, reading: MeterReading | None
) -> MeteredChargeDetail | None:
    if reading is None or charge.common_cents is None:
        return None
    return MeteredChargeDetail(
        previous_reading=from_milli(reading.previous_milli),
        current_reading=from_milli(reading.current_milli),
        consumption=from_milli(reading.consumption_milli),
        own_amount=Decimal(charge.amount_cents - charge.common_cents).scaleb(-2),
        common_amount=Decimal(charge.common_cents).scaleb(-2),
        rolled_over=reading.current_milli < reading.previous_milli,
    )


def building_invoices(building_id: UUID):
    return (
        select(ServiceInvoice, ServiceCategory.name)
        .join(ServiceCategory, ServiceCategory.id == ServiceInvoice.category_id)
        .where(ServiceCategory.building_id == building_id)
    )


def list_invoices(db: Session, building_id: UUID) -> list[InvoiceSummary]:
    if not building_exists(db, building_id):
        raise InvoiceNotFound("Edificio no encontrado.")
    rows = db.execute(
        building_invoices(building_id).order_by(
            ServiceInvoice.billing_year.desc(),
            ServiceInvoice.billing_month.desc(),
            func.lower(ServiceCategory.name),
            ServiceInvoice.id,
        )
    )
    return [summarize(invoice, category_name) for invoice, category_name in rows]


def scoped_invoice(
    db: Session, building_id: UUID, invoice_id: UUID, *, read: bool
) -> tuple[ServiceInvoice, str]:
    row = db.execute(
        building_invoices(building_id)
        .where(ServiceInvoice.id == invoice_id)
        .with_for_update(of=ServiceInvoice, read=read)
    ).one_or_none()
    if row is None:
        raise InvoiceNotFound("Factura no encontrada.")
    return row[0], row[1]


def invoice_records(
    db: Session, invoice: ServiceInvoice
) -> tuple[Sequence[UnitCharge], Sequence[MeterReading]]:
    charges = db.scalars(
        select(UnitCharge)
        .where(UnitCharge.invoice_id == invoice.id)
        .order_by(func.lower(UnitCharge.unit_number), UnitCharge.unit_id)
    ).all()
    readings = (
        db.scalars(
            select(MeterReading).where(MeterReading.invoice_id == invoice.id)
        ).all()
        if invoice.total_volume_milli is not None
        else ()
    )
    return charges, readings


def correction_history(db: Session, invoice_id: UUID) -> list[CorrectionDetail]:
    rows = db.execute(
        select(
            InvoiceCorrection.revision,
            InvoiceCorrection.reason,
            Account.username,
            InvoiceCorrection.corrected_at,
        )
        .join(Account, Account.id == InvoiceCorrection.corrected_by_id)
        .where(InvoiceCorrection.invoice_id == invoice_id)
        .order_by(InvoiceCorrection.revision.desc())
    )
    return [
        CorrectionDetail(
            revision=revision,
            reason=reason,
            corrected_by=username,
            corrected_at=corrected_at,
        )
        for revision, reason, username, corrected_at in rows
    ]


def find_invoice(db: Session, building_id: UUID, invoice_id: UUID) -> InvoiceDetail:
    invoice, category_name = scoped_invoice(db, building_id, invoice_id, read=True)
    charges, readings = invoice_records(db, invoice)
    detail = invoice_detail(invoice, category_name, charges, readings)
    detail.corrections = correction_history(db, invoice.id)
    return detail


def scoped_category(
    db: Session, building_id: UUID, category_id: UUID
) -> ServiceCategory:
    category = db.scalar(
        select(ServiceCategory).where(
            ServiceCategory.id == category_id,
            ServiceCategory.building_id == building_id,
        )
    )
    if category is None:
        raise InvoiceNotFound("Servicio no encontrado en este edificio.")
    return category


def building_units(db: Session, building_id: UUID) -> list[tuple[UUID, str]]:
    rows = db.execute(
        select(Unit.id, Unit.number)
        .where(Unit.building_id == building_id)
        .order_by(func.lower(Unit.number), Unit.id)
    )
    return [(unit_id, number) for unit_id, number in rows]


def reading_defaults(
    db: Session, building_id: UUID, category_id: UUID, period: AccountingPeriod
) -> list[MeterReadingDefaults]:
    category = scoped_category(db, building_id, category_id)
    if category.calculation_type != CalculationType.METERED:
        raise InvoiceConflict("Selecciona un servicio por consumo medido.")
    readings = neighboring_readings(db, category_id, period)
    return [
        MeterReadingDefaults(
            unit_id=unit_id,
            unit_number=number,
            previous_reading=from_milli(readings[unit_id])
            if unit_id in readings
            else None,
        )
        for unit_id, number in building_units(db, building_id)
    ]


def create_invoice(
    db: Session, building_id: UUID, data: LinearInvoiceInput | MeteredInvoiceInput
) -> InvoiceDetail:
    # Unit registration and invoice issuance serialize on the building.
    if lock_building(db, building_id) is None:
        raise InvoiceNotFound("Edificio no encontrado.")
    category = scoped_category(db, building_id, data.category_id)
    if isinstance(data, MeteredInvoiceInput) != (
        category.calculation_type == CalculationType.METERED
    ):
        raise InvoiceConflict(
            "La factura debe coincidir con el tipo de reparto del servicio."
        )
    units = building_units(db, building_id)
    if not units:
        raise InvoiceConflict("Registra al menos una unidad antes de emitir cargos.")

    invoice = ServiceInvoice(
        **data.model_dump(exclude={"total_amount", "total_volume", "readings"}),
        total_cents=int(data.total_amount.scaleb(2)),
        total_volume_milli=to_milli(data.total_volume)
        if isinstance(data, MeteredInvoiceInput)
        else None,
    )
    try:
        db.add(invoice)
        db.flush()
        readings: list[MeterReading] = []
        if isinstance(data, MeteredInvoiceInput):
            charges, readings = metered_records(
                db, invoice, units, data, total_cents=invoice.total_cents
            )
            db.add_all(readings)
        else:
            amounts = split_linear(invoice.total_cents, len(units))
            charges = [
                UnitCharge(
                    invoice_id=invoice.id,
                    unit_id=unit_id,
                    unit_number=number,
                    amount_cents=amount,
                )
                for (unit_id, number), amount in zip(units, amounts, strict=True)
            ]
        db.add_all(charges)
        result = invoice_detail(invoice, category.name, charges, readings)
        db.commit()
    except InvoiceConflict:
        db.rollback()
        raise
    except IntegrityError as error:
        db.rollback()
        if (
            isinstance(error.orig, UniqueViolation)
            and error.orig.diag.constraint_name == INVOICE_PERIOD_CONSTRAINT
        ):
            raise InvoiceConflict(
                "Ya existe una factura de este servicio para el periodo."
            ) from error
        raise
    return result
