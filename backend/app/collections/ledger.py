"""Credit consumption and carry snapshots within the caller's building transaction."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import BigInteger, and_, cast, func, select
from sqlalchemy.orm import Session

from app.billing.models import MeterReading, ServiceCategory, ServiceInvoice, UnitCharge
from app.collections.models import BalanceCarryForward, Payment, PaymentApplication
from app.properties.models import Unit


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


def settle_unit(
    db: Session,
    unit_id: UUID,
    actor_id: UUID | None,
    *,
    new_payment_id: UUID | None = None,
) -> None:
    """The caller holds the building lock; all writes commit with its operation."""
    db.flush()
    rows = charge_rows(db, unit_id)
    balances = {
        charge.id: charge.amount_cents - applied for charge, _, _, applied, _ in rows
    }
    credits = db.scalars(
        select(Payment)
        .where(Payment.unit_id == unit_id, Payment.credit_cents > 0)
        .order_by(Payment.recorded_at, Payment.id)
    ).all()
    now = datetime.now(UTC)
    for payment in credits:
        for charge, invoice, _, _, _ in rows:
            if payment.credit_cents == 0:
                break
            amount = min(balances[charge.id], payment.credit_cents)
            if amount <= 0:
                continue
            db.add(
                PaymentApplication(
                    payment_id=payment.id,
                    charge_id=charge.id,
                    amount_cents=amount,
                    applied_at=now,
                    applied_by_id=actor_id,
                    automatic=payment.id != new_payment_id,
                )
            )
            payment.credit_cents -= amount
            balances[charge.id] -= amount
            if invoice.accounting_locked_at is None:
                invoice.accounting_locked_at = now

    periods = sorted(
        {(invoice.billing_year, invoice.billing_month) for _, invoice, _, _, _ in rows}
    )
    existing = set(
        db.execute(
            select(
                BalanceCarryForward.charge_id,
                BalanceCarryForward.billing_year,
                BalanceCarryForward.billing_month,
            )
            .join(UnitCharge, UnitCharge.id == BalanceCarryForward.charge_id)
            .where(UnitCharge.unit_id == unit_id)
        ).all()
    )
    for charge, invoice, _, _, _ in rows:
        balance = balances[charge.id]
        if balance <= 0:
            continue
        origin = (invoice.billing_year, invoice.billing_month)
        for year, month in periods:
            if (year, month) <= origin or (charge.id, year, month) in existing:
                continue
            db.add(
                BalanceCarryForward(
                    charge_id=charge.id,
                    billing_year=year,
                    billing_month=month,
                    amount_cents=balance,
                    recorded_by_id=actor_id,
                    recorded_at=now,
                )
            )
            if invoice.accounting_locked_at is None:
                invoice.accounting_locked_at = now
    db.flush()


def settle_building(db: Session, building_id: UUID, actor_id: UUID | None) -> None:
    for unit_id in db.scalars(
        select(Unit.id).where(Unit.building_id == building_id).order_by(Unit.id)
    ):
        settle_unit(db, unit_id, actor_id)
