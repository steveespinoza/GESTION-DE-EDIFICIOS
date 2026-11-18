from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.billing.adjustment_schemas import ChargeAdjustmentDetail, ChargeAdjustmentInput
from app.billing.errors import InvoiceConflict, InvoiceNotFound
from app.billing.models import (
    ChargeAdjustment,
    ServiceCategory,
    ServiceInvoice,
    UnitCharge,
)
from app.collections.ledger import adjustment_cents, released_cents, settle_unit
from app.collections.models import (
    Payment,
    PaymentApplication,
    PaymentApplicationRelease,
)
from app.identity.models import Account
from app.properties.service import lock_building


def money(cents: int) -> Decimal:
    return Decimal(cents).scaleb(-2)


def adjustment_history(
    db: Session, *, invoice_id: UUID | None = None, unit_id: UUID | None = None
) -> list[ChargeAdjustmentDetail]:
    released = (
        select(func.coalesce(func.sum(PaymentApplicationRelease.amount_cents), 0))
        .where(PaymentApplicationRelease.adjustment_id == ChargeAdjustment.id)
        .correlate(ChargeAdjustment)
        .scalar_subquery()
    )
    query = (
        select(
            ChargeAdjustment,
            UnitCharge.unit_number,
            Account.username,
            released,
            ServiceInvoice,
            ServiceCategory.name,
        )
        .join(UnitCharge, UnitCharge.id == ChargeAdjustment.charge_id)
        .join(ServiceInvoice, ServiceInvoice.id == UnitCharge.invoice_id)
        .join(ServiceCategory, ServiceCategory.id == ServiceInvoice.category_id)
        .join(Account, Account.id == ChargeAdjustment.recorded_by_id)
        .where(
            UnitCharge.invoice_id == invoice_id
            if invoice_id is not None
            else UnitCharge.unit_id == unit_id
        )
        .order_by(ChargeAdjustment.recorded_at, ChargeAdjustment.id)
    )
    return [
        ChargeAdjustmentDetail(
            id=adjustment.id,
            charge_id=adjustment.charge_id,
            unit_number=number,
            service=service,
            billing_year=invoice.billing_year,
            billing_month=invoice.billing_month,
            revision=adjustment.revision,
            previous_amount=money(adjustment.previous_cents),
            new_amount=money(adjustment.revised_cents),
            difference=money(adjustment.delta_cents),
            released_credit=money(released_amount),
            reason=adjustment.reason,
            recorded_by=author,
            recorded_at=adjustment.recorded_at.astimezone(UTC),
        )
        for adjustment, number, author, released_amount, invoice, service in db.execute(
            query
        )
    ]


def release_excess(
    db: Session, charge: UnitCharge, adjustment: ChargeAdjustment
) -> None:
    rows = db.execute(
        select(PaymentApplication, Payment, released_cents())
        .join(Payment, Payment.id == PaymentApplication.payment_id)
        .where(PaymentApplication.charge_id == charge.id)
        .order_by(PaymentApplication.applied_at.desc(), PaymentApplication.id.desc())
    ).all()
    excess = (
        sum(application.amount_cents - released for application, _, released in rows)
        - adjustment.revised_cents
    )
    for application, payment, released in rows:
        if excess <= 0:
            break
        amount = min(excess, application.amount_cents - released)
        if amount <= 0:
            continue
        db.add(
            PaymentApplicationRelease(
                application_id=application.id,
                adjustment_id=adjustment.id,
                amount_cents=amount,
            )
        )
        payment.credit_cents += amount
        excess -= amount


def adjust_charge(
    db: Session,
    building_id: UUID,
    invoice_id: UUID,
    charge_id: UUID,
    data: ChargeAdjustmentInput,
    actor_id: UUID,
) -> tuple[ChargeAdjustmentDetail, bool]:
    if lock_building(db, building_id) is None:
        raise InvoiceNotFound("Cargo no encontrado.")
    row = db.execute(
        select(UnitCharge, ServiceInvoice, adjustment_cents())
        .join(ServiceInvoice, ServiceInvoice.id == UnitCharge.invoice_id)
        .join(ServiceCategory, ServiceCategory.id == ServiceInvoice.category_id)
        .where(
            UnitCharge.id == charge_id,
            ServiceInvoice.id == invoice_id,
            ServiceCategory.building_id == building_id,
        )
    ).one_or_none()
    if row is None:
        raise InvoiceNotFound("Cargo no encontrado.")
    charge, invoice, delta = row
    existing = db.scalar(
        select(ChargeAdjustment).where(
            ChargeAdjustment.charge_id == charge.id,
            ChargeAdjustment.request_id == data.request_id,
        )
    )
    revised = int(data.new_amount.scaleb(2))
    if existing is not None:
        if (existing.revision, existing.revised_cents, existing.reason) != (
            data.revision + 1,
            revised,
            data.reason,
        ):
            raise InvoiceConflict(
                "Esta solicitud ya se usó para otro ajuste. Revisa el historial."
            )
        return next(
            item
            for item in adjustment_history(db, invoice_id=invoice.id)
            if item.id == existing.id
        ), False
    if invoice.accounting_locked_at is None:
        raise InvoiceConflict(
            "La factura está abierta. Corrígela desde su formulario de corrección."
        )
    revision = db.scalar(
        select(func.coalesce(func.max(ChargeAdjustment.revision), 0)).where(
            ChargeAdjustment.charge_id == charge.id
        )
    )
    if revision != data.revision:
        raise InvoiceConflict(
            "El cargo cambió. Actualiza la factura antes de registrar el ajuste."
        )
    previous = charge.amount_cents + delta
    if revised == previous:
        raise InvoiceConflict(
            "El nuevo importe debe ser diferente del importe vigente."
        )
    adjustment = ChargeAdjustment(
        charge_id=charge.id,
        request_id=data.request_id,
        revision=revision + 1,
        previous_cents=previous,
        revised_cents=revised,
        delta_cents=revised - previous,
        reason=data.reason,
        recorded_by_id=actor_id,
        recorded_at=datetime.now(UTC),
    )
    db.add(adjustment)
    db.flush()
    release_excess(db, charge, adjustment)
    settle_unit(db, charge.unit_id, actor_id)
    result = next(
        item
        for item in adjustment_history(db, invoice_id=invoice.id)
        if item.id == adjustment.id
    )
    db.commit()
    return result, True
