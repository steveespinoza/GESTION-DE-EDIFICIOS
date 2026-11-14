from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Building(Base):
    __tablename__ = "buildings"
    __table_args__ = (
        CheckConstraint(
            "total_units >= 0", name="ck_buildings_total_units_nonnegative"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(150))
    address: Mapped[str | None] = mapped_column(String(250))
    total_units: Mapped[int]
    bank_name: Mapped[str | None] = mapped_column(String(150))
    account_number: Mapped[str | None] = mapped_column(String(64))
    cci: Mapped[str | None] = mapped_column(String(64))
    account_holder: Mapped[str | None] = mapped_column(String(150))
    contact_email: Mapped[str | None] = mapped_column(String(254))


class Unit(Base):
    __tablename__ = "units"
    __table_args__ = (
        UniqueConstraint("building_id", "number", name="uq_units_building_number"),
        CheckConstraint("area_sqm > 0", name="ck_units_positive_area"),
        Index("ix_units_owner_id", "owner_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    building_id: Mapped[UUID] = mapped_column(ForeignKey("buildings.id"))
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"))
    number: Mapped[str] = mapped_column(String(60))
    area_sqm: Mapped[Decimal] = mapped_column(Numeric(12, 2))
