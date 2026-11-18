from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CollectionDeadline(Base):
    __tablename__ = "collection_deadlines"
    __table_args__ = (
        UniqueConstraint(
            "building_id", "request_id", name="uq_collection_deadlines_request"
        ),
        UniqueConstraint(
            "building_id",
            "billing_year",
            "billing_month",
            "revision",
            name="uq_collection_deadlines_revision",
        ),
        CheckConstraint(
            "billing_year BETWEEN 2020 AND 9999", name="ck_collection_deadlines_year"
        ),
        CheckConstraint(
            "billing_month BETWEEN 1 AND 12", name="ck_collection_deadlines_month"
        ),
        CheckConstraint("revision >= 1", name="ck_collection_deadlines_revision"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    building_id: Mapped[UUID] = mapped_column(ForeignKey("buildings.id"))
    billing_year: Mapped[int]
    billing_month: Mapped[int]
    revision: Mapped[int]
    request_id: Mapped[UUID]
    due_date: Mapped[date]
    reason: Mapped[str] = mapped_column(String(500))
    recorded_by_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("unit_id", "request_id", name="uq_payments_unit_request"),
        CheckConstraint(
            "amount_cents BETWEEN 1 AND 999999999999", name="ck_payments_amount"
        ),
        CheckConstraint(
            "credit_cents BETWEEN 0 AND amount_cents", name="ck_payments_credit"
        ),
        CheckConstraint("billing_year BETWEEN 2020 AND 9999", name="ck_payments_year"),
        CheckConstraint("billing_month BETWEEN 1 AND 12", name="ck_payments_month"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    unit_id: Mapped[UUID] = mapped_column(ForeignKey("units.id"))
    request_id: Mapped[UUID]
    billing_year: Mapped[int]
    billing_month: Mapped[int]
    received_on: Mapped[date]
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    credit_cents: Mapped[int] = mapped_column(BigInteger)
    reference: Mapped[str | None] = mapped_column(String(120))
    recorded_by_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PaymentApplication(Base):
    __tablename__ = "payment_applications"
    __table_args__ = (
        CheckConstraint(
            "amount_cents BETWEEN 1 AND 999999999999",
            name="ck_payment_applications_amount",
        ),
        Index("ix_payment_applications_charge_id", "charge_id"),
        Index("ix_payment_applications_payment_id", "payment_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    payment_id: Mapped[UUID] = mapped_column(ForeignKey("payments.id"))
    charge_id: Mapped[UUID] = mapped_column(ForeignKey("unit_charges.id"))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    applied_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("accounts.id"))
    automatic: Mapped[bool] = mapped_column(default=False, server_default="false")


class PaymentApplicationRelease(Base):
    __tablename__ = "payment_application_releases"
    __table_args__ = (
        CheckConstraint(
            "amount_cents BETWEEN 1 AND 999999999999",
            name="ck_application_releases_amount",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("payment_applications.id"), primary_key=True
    )
    adjustment_id: Mapped[UUID] = mapped_column(
        ForeignKey("charge_adjustments.id"), primary_key=True
    )
    amount_cents: Mapped[int] = mapped_column(BigInteger)


class BalanceCarryForward(Base):
    __tablename__ = "balance_carry_forwards"
    __table_args__ = (
        CheckConstraint("billing_year BETWEEN 2020 AND 9999", name="ck_carry_year"),
        CheckConstraint("billing_month BETWEEN 1 AND 12", name="ck_carry_month"),
        CheckConstraint(
            "amount_cents BETWEEN 1 AND 999999999999", name="ck_carry_amount"
        ),
    )

    charge_id: Mapped[UUID] = mapped_column(
        ForeignKey("unit_charges.id"), primary_key=True
    )
    billing_year: Mapped[int] = mapped_column(primary_key=True)
    billing_month: Mapped[int] = mapped_column(primary_key=True)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    recorded_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("accounts.id"))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
