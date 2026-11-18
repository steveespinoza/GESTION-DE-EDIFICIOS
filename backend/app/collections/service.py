from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.adjustments import adjustment_history
from app.billing.metering import from_milli
from app.billing.models import ServiceCategory, ServiceInvoice, UnitCharge
from app.collections.ledger import charge_rows, released_cents, settle_unit
from app.collections.models import BalanceCarryForward, Payment, PaymentApplication
from app.collections.schemas import (
    AppliedCharge,
    CarryForwardDetail,
    PaymentDetail,
    PaymentInput,
    Statement,
    StatementCharge,
)
from app.identity.models import Account
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


def payment_details(
    db: Session, unit_id: UUID, payment_id: UUID | None = None
) -> list[PaymentDetail]:
    query = (
        select(
            Payment,
            PaymentApplication,
            ServiceInvoice,
            ServiceCategory.name,
            Account.username,
            released_cents(),
        )
        .outerjoin(PaymentApplication, Payment.id == PaymentApplication.payment_id)
        .outerjoin(UnitCharge, UnitCharge.id == PaymentApplication.charge_id)
        .outerjoin(ServiceInvoice, ServiceInvoice.id == UnitCharge.invoice_id)
        .outerjoin(ServiceCategory, ServiceCategory.id == ServiceInvoice.category_id)
        .outerjoin(Account, Account.id == PaymentApplication.applied_by_id)
        .where(Payment.unit_id == unit_id)
        .order_by(
            Payment.received_on.desc(),
            Payment.recorded_at.desc(),
            Payment.id,
            ServiceInvoice.billing_year,
            ServiceInvoice.billing_month,
            ServiceInvoice.end_date,
            ServiceInvoice.id,
            PaymentApplication.applied_at,
            PaymentApplication.id,
        )
    )
    if payment_id is not None:
        query = query.where(Payment.id == payment_id)
    details: dict[UUID, PaymentDetail] = {}
    for payment, application, invoice, service, actor, released in db.execute(query):
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
                    id=application.id,
                    charge_id=application.charge_id,
                    service=service,
                    amount=money(application.amount_cents),
                    released=money(released),
                    net_amount=money(application.amount_cents - released),
                    applied_at=application.applied_at.astimezone(UTC),
                    applied_by=actor,
                    automatic=application.automatic,
                    billing_year=invoice.billing_year,
                    billing_month=invoice.billing_month,
                )
            )
    return list(details.values())


def carry_details(
    db: Session, unit_id: UUID, balances: dict[UUID, Decimal]
) -> list[CarryForwardDetail]:
    rows = db.execute(
        select(
            BalanceCarryForward, ServiceInvoice, ServiceCategory.name, Account.username
        )
        .join(UnitCharge, UnitCharge.id == BalanceCarryForward.charge_id)
        .join(ServiceInvoice, ServiceInvoice.id == UnitCharge.invoice_id)
        .join(ServiceCategory, ServiceCategory.id == ServiceInvoice.category_id)
        .outerjoin(Account, Account.id == BalanceCarryForward.recorded_by_id)
        .where(UnitCharge.unit_id == unit_id)
        .order_by(
            BalanceCarryForward.billing_year,
            BalanceCarryForward.billing_month,
            ServiceInvoice.billing_year,
            ServiceInvoice.billing_month,
            UnitCharge.id,
        )
    )
    return [
        CarryForwardDetail(
            charge_id=carry.charge_id,
            billing_year=carry.billing_year,
            billing_month=carry.billing_month,
            source_year=invoice.billing_year,
            source_month=invoice.billing_month,
            service=service,
            amount=money(carry.amount_cents),
            balance=balances[carry.charge_id],
            recorded_at=carry.recorded_at.astimezone(UTC),
            recorded_by=actor,
        )
        for carry, invoice, service, actor in rows
    ]


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
            amount=money(charge.amount_cents + adjustment),
            original_amount=money(charge.amount_cents),
            adjustment=money(adjustment),
            applied=money(applied),
            balance=money(charge.amount_cents + adjustment - applied),
            consumption=from_milli(consumption) if consumption is not None else None,
        )
        for charge, invoice, service, applied, consumption, adjustment in charge_rows(
            db, unit.id
        )
    ]
    payments = payment_details(db, unit.id)
    return Statement(
        unit_number=unit.number,
        building_name=building.name,
        balance=sum((charge.balance for charge in charges), money(0)),
        credit=sum((payment.credit for payment in payments), money(0)),
        charges=charges,
        payments=payments,
        carry_forwards=carry_details(
            db, unit.id, {charge.id: charge.balance for charge in charges}
        ),
        adjustments=adjustment_history(db, unit_id=unit.id),
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

    payment = Payment(
        **attributes,
        credit_cents=total,
        recorded_by_id=user_id,
        recorded_at=datetime.now(UTC),
    )
    db.add(payment)
    db.flush()
    settle_unit(db, unit_id, user_id, new_payment_id=payment.id)
    result = payment_details(db, unit_id, payment.id)[0]
    return result, True
