from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import BigInteger, and_, cast, func, select
from sqlalchemy.orm import Session

from app.billing.metering import from_milli
from app.billing.models import MeterReading, ServiceCategory, ServiceInvoice, UnitCharge
from app.collections.models import Payment, PaymentApplication
from app.collections.schemas import (
    AppliedCharge,
    PaymentDetail,
    PaymentInput,
    Statement,
    StatementCharge,
)
from app.properties.models import Building, Unit
from app.properties.service import lock_building


class UnitNotFound(Exception):
    pass


class PaymentConflict(Exception):
    pass


def money(cents: int) -> Decimal:
    return Decimal(cents).scaleb(-2)


def unit_in_building(db: Session, building_id: UUID, unit_id: UUID) -> Unit:
    unit = db.scalar(
        select(Unit).where(Unit.id == unit_id, Unit.building_id == building_id)
    )
    if unit is None:
        raise UnitNotFound
    return unit


def charge_rows(db: Session, unit_id: UUID):
    applied = (
        select(
            cast(
                func.coalesce(func.sum(PaymentApplication.amount_cents), 0), BigInteger
            )
        )
        .where(PaymentApplication.charge_id == UnitCharge.id)
        .scalar_subquery()
    )
    return db.execute(
        select(
            UnitCharge,
            ServiceInvoice,
            ServiceCategory.name,
            applied,
            MeterReading.consumption_milli,
        )
        .join(ServiceInvoice, UnitCharge.invoice_id == ServiceInvoice.id)
        .join(ServiceCategory, ServiceInvoice.category_id == ServiceCategory.id)
        .outerjoin(
            MeterReading,
            and_(
                MeterReading.invoice_id == UnitCharge.invoice_id,
                MeterReading.unit_id == UnitCharge.unit_id,
            ),
        )
        .where(UnitCharge.unit_id == unit_id)
        .order_by(
            ServiceInvoice.billing_year,
            ServiceInvoice.billing_month,
            ServiceInvoice.end_date,
            ServiceInvoice.id,
        )
    ).all()


def payment_details(
    db: Session, unit_id: UUID, payment_id: UUID | None = None
) -> list[PaymentDetail]:
    query = (
        select(Payment, PaymentApplication, ServiceInvoice, ServiceCategory.name)
        .outerjoin(PaymentApplication, Payment.id == PaymentApplication.payment_id)
        .outerjoin(UnitCharge, UnitCharge.id == PaymentApplication.charge_id)
        .outerjoin(ServiceInvoice, ServiceInvoice.id == UnitCharge.invoice_id)
        .outerjoin(ServiceCategory, ServiceCategory.id == ServiceInvoice.category_id)
        .where(Payment.unit_id == unit_id)
        .order_by(
            Payment.received_on.desc(),
            Payment.recorded_at.desc(),
            Payment.id,
            ServiceInvoice.billing_year,
            ServiceInvoice.billing_month,
            ServiceInvoice.end_date,
            ServiceInvoice.id,
        )
    )
    if payment_id is not None:
        query = query.where(Payment.id == payment_id)
    details: dict[UUID, PaymentDetail] = {}
    for payment, application, invoice, service in db.execute(query):
        if payment.id not in details:
            details[payment.id] = PaymentDetail(
                id=payment.id,
                billing_year=payment.billing_year,
                billing_month=payment.billing_month,
                received_on=payment.received_on,
                amount=money(payment.amount_cents),
                credit=money(payment.credit_cents),
                reference=payment.reference,
            )
        if application is not None:
            details[payment.id].applications.append(
                AppliedCharge(
                    charge_id=application.charge_id,
                    service=service,
                    amount=money(application.amount_cents),
                    billing_year=invoice.billing_year,
                    billing_month=invoice.billing_month,
                )
            )
    return list(details.values())


def read_statement(
    db: Session,
    unit_id: UUID,
    *,
    building_id: UUID | None = None,
    owner_id: UUID | None = None,
) -> Statement:
    query = (
        select(Building, Unit)
        .join(Unit, Unit.building_id == Building.id)
        .where(Unit.id == unit_id)
    )
    scope = (
        Building.id == building_id
        if building_id is not None
        else Unit.owner_id == owner_id
    )
    # Charges, payments and the unit are read from a consistent state while writers wait.
    row = db.execute(
        query.where(scope).with_for_update(read=True, of=Building)
    ).one_or_none()
    if row is None:
        raise UnitNotFound
    building, unit = row
    charges = [
        StatementCharge(
            id=charge.id,
            billing_year=invoice.billing_year,
            billing_month=invoice.billing_month,
            service=service,
            coverage_end=invoice.end_date,
            amount=money(charge.amount_cents),
            applied=money(applied),
            balance=money(charge.amount_cents - applied),
            consumption=from_milli(consumption) if consumption is not None else None,
        )
        for charge, invoice, service, applied, consumption in charge_rows(db, unit.id)
    ]
    payments = payment_details(db, unit.id)
    return Statement(
        unit_number=unit.number,
        building_name=building.name,
        balance=sum((charge.balance for charge in charges), money(0)),
        credit=sum((payment.credit for payment in payments), money(0)),
        charges=charges,
        payments=payments,
    )


def record_payment(
    db: Session, building_id: UUID, unit_id: UUID, user_id: UUID, data: PaymentInput
) -> tuple[PaymentDetail, bool]:
    # Issuance, invoice corrections and payments in the building acquire this lock first.
    if lock_building(db, building_id) is None:
        raise UnitNotFound
    unit_in_building(db, building_id, unit_id)
    result = stage_payment(db, unit_id, user_id, data)
    db.commit()
    return result


def stage_payment(
    db: Session, unit_id: UUID, user_id: UUID, data: PaymentInput
) -> tuple[PaymentDetail, bool]:
    """Apply a payment in the caller's transaction while it holds the building lock."""
    total = int(data.amount.scaleb(2))
    attributes = {
        "unit_id": unit_id,
        "request_id": data.request_id,
        "billing_year": data.billing_year,
        "billing_month": data.billing_month,
        "received_on": data.received_on,
        "amount_cents": total,
        "reference": data.reference,
    }
    existing = db.scalar(
        select(Payment).filter_by(unit_id=unit_id, request_id=data.request_id)
    )
    if existing is not None:
        if any(getattr(existing, key) != value for key, value in attributes.items()):
            raise PaymentConflict(
                "Este registro se usó para otro pago. Revisa el historial."
            )
        return payment_details(db, unit_id, existing.id)[0], False

    payment = Payment(**attributes, credit_cents=total, recorded_by_id=user_id)
    db.add(payment)
    db.flush()
    cutoff = (data.billing_year, data.billing_month)
    recorded_at = datetime.now(UTC)
    for charge, invoice, _, applied, _ in charge_rows(db, unit_id):
        if (
            payment.credit_cents == 0
            or (invoice.billing_year, invoice.billing_month) > cutoff
        ):
            break
        amount = min(charge.amount_cents - applied, payment.credit_cents)
        if amount <= 0:
            continue
        db.add(
            PaymentApplication(
                payment_id=payment.id, charge_id=charge.id, amount_cents=amount
            )
        )
        payment.credit_cents -= amount
        if invoice.accounting_locked_at is None:
            invoice.accounting_locked_at = recorded_at
    result = payment_details(db, unit_id, payment.id)[0]
    return result, True
