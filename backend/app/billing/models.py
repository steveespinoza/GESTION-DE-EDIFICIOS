from datetime import date
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

SERVICE_NAME_INDEX = "uq_service_categories_building_name_ci"
INVOICE_PERIOD_CONSTRAINT = "uq_service_invoices_category_period"


class CalculationType(StrEnum):
    LINEAR = "LINEAR"
    METERED = "METERED"


class ServiceCategory(Base):
    __tablename__ = "service_categories"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    building_id: Mapped[UUID] = mapped_column(ForeignKey("buildings.id"))
    name: Mapped[str] = mapped_column(String(50))
    calculation_type: Mapped[CalculationType] = mapped_column(
        Enum(
            CalculationType,
            name="ck_service_categories_calculation_type",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        )
    )

    __table_args__ = (
        Index(SERVICE_NAME_INDEX, "building_id", func.lower(name), unique=True),
    )


class ServiceInvoice(Base):
    __tablename__ = "service_invoices"
    __table_args__ = (
        UniqueConstraint(
            "category_id",
            "billing_year",
            "billing_month",
            name=INVOICE_PERIOD_CONSTRAINT,
        ),
        CheckConstraint(
            "billing_year BETWEEN 2020 AND 9999",
            name="ck_service_invoices_billing_year",
        ),
        CheckConstraint(
            "billing_month BETWEEN 1 AND 12", name="ck_service_invoices_billing_month"
        ),
        CheckConstraint(
            "end_date >= start_date", name="ck_service_invoices_date_order"
        ),
        CheckConstraint(
            "total_cents BETWEEN 1 AND 999999999999", name="ck_service_invoices_total"
        ),
        CheckConstraint(
            "total_volume_milli BETWEEN 1 AND 999999999999",
            name="ck_service_invoices_volume",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    category_id: Mapped[UUID] = mapped_column(ForeignKey("service_categories.id"))
    billing_year: Mapped[int]
    billing_month: Mapped[int]
    start_date: Mapped[date]
    end_date: Mapped[date]
    total_cents: Mapped[int] = mapped_column(BigInteger)
    total_volume_milli: Mapped[int | None] = mapped_column(BigInteger)


class UnitCharge(Base):
    __tablename__ = "unit_charges"
    __table_args__ = (
        UniqueConstraint("invoice_id", "unit_id", name="uq_unit_charges_invoice_unit"),
        CheckConstraint(
            "amount_cents BETWEEN 0 AND 999999999999", name="ck_unit_charges_amount"
        ),
        Index("ix_unit_charges_unit_id", "unit_id"),
        CheckConstraint(
            "common_cents BETWEEN 0 AND amount_cents",
            name="ck_unit_charges_common_amount",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("service_invoices.id"))
    unit_id: Mapped[UUID] = mapped_column(ForeignKey("units.id"))
    unit_number: Mapped[str] = mapped_column(String(60))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    common_cents: Mapped[int | None] = mapped_column(BigInteger)


class MeterReading(Base):
    __tablename__ = "meter_readings"
    __table_args__ = (
        CheckConstraint(
            "previous_milli BETWEEN 0 AND 99999999", name="ck_meter_readings_previous"
        ),
        CheckConstraint(
            "current_milli BETWEEN 0 AND 99999999", name="ck_meter_readings_current"
        ),
        CheckConstraint(
            "consumption_milli = CASE WHEN current_milli < previous_milli "
            "THEN 100000000 + current_milli - previous_milli ELSE current_milli - previous_milli END",
            name="ck_meter_readings_consumption",
        ),
    )

    invoice_id: Mapped[UUID] = mapped_column(
        ForeignKey("service_invoices.id"), primary_key=True
    )
    unit_id: Mapped[UUID] = mapped_column(ForeignKey("units.id"), primary_key=True)
    previous_milli: Mapped[int]
    current_milli: Mapped[int]
    consumption_milli: Mapped[int]
