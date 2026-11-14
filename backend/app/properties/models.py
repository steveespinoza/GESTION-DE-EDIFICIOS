from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, String, Uuid
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
