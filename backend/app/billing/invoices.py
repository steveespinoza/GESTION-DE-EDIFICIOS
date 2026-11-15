from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from psycopg.errors import UniqueViolation
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billing.allocation import split_linear
from app.billing.catalog import building_exists
from app.billing.invoice_schemas import (
    ChargeDetail,
    InvoiceDetail,
    InvoiceSummary,
    LinearInvoiceInput,
)
from app.billing.models import (
    INVOICE_PERIOD_CONSTRAINT,
    CalculationType,
    ServiceCategory,
    ServiceInvoice,
    UnitCharge,
)
from app.properties.models import Unit
from app.properties.service import lock_building


class InvoiceNotFound(Exception):
    pass


class InvoiceConflict(Exception):
    pass


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
    invoice: ServiceInvoice, category_name: str, charges: Sequence[UnitCharge]
) -> InvoiceDetail:
    return InvoiceDetail(
        **summarize(invoice, category_name).model_dump(),
        charges=[
            ChargeDetail(
                unit_id=charge.unit_id,
                unit_number=charge.unit_number,
                amount=Decimal(charge.amount_cents).scaleb(-2),
            )
            for charge in charges
        ],
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


def find_invoice(db: Session, building_id: UUID, invoice_id: UUID) -> InvoiceDetail:
    row = db.execute(
        building_invoices(building_id).where(ServiceInvoice.id == invoice_id)
    ).one_or_none()
    if row is None:
        raise InvoiceNotFound("Factura no encontrada.")
    invoice, category_name = row
    charges = db.scalars(
        select(UnitCharge)
        .where(UnitCharge.invoice_id == invoice.id)
        .order_by(func.lower(UnitCharge.unit_number), UnitCharge.unit_id)
    ).all()
    return invoice_detail(invoice, category_name, charges)


def create_linear_invoice(
    db: Session, building_id: UUID, data: LinearInvoiceInput
) -> InvoiceDetail:
    # Unit registration holds the same lock until its transaction commits.
    if lock_building(db, building_id) is None:
        raise InvoiceNotFound("Edificio no encontrado.")
    category = db.scalar(
        select(ServiceCategory).where(
            ServiceCategory.id == data.category_id,
            ServiceCategory.building_id == building_id,
        )
    )
    if category is None:
        raise InvoiceNotFound("Servicio no encontrado en este edificio.")
    if category.calculation_type != CalculationType.LINEAR:
        raise InvoiceConflict("Selecciona un servicio con reparto lineal.")
    units = db.execute(
        select(Unit.id, Unit.number)
        .where(Unit.building_id == building_id)
        .order_by(func.lower(Unit.number), Unit.id)
    ).all()
    if not units:
        raise InvoiceConflict("Registra al menos una unidad antes de emitir cargos.")

    invoice = ServiceInvoice(
        **data.model_dump(exclude={"total_amount"}),
        total_cents=int(data.total_amount.scaleb(2)),
    )
    try:
        db.add(invoice)
        db.flush()
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
        result = invoice_detail(invoice, category.name, charges)
        db.commit()
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
