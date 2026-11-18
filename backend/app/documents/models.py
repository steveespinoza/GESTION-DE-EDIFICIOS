from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.storage.files import MAX_FILE_BYTES


class Receipt(Base):
    __tablename__ = "receipts"
    __table_args__ = (
        UniqueConstraint("unit_id", "request_id", name="uq_receipts_request"),
        UniqueConstraint(
            "unit_id",
            "billing_year",
            "billing_month",
            "version",
            name="uq_receipts_version",
        ),
        CheckConstraint("billing_year BETWEEN 2020 AND 9999", name="ck_receipts_year"),
        CheckConstraint("billing_month BETWEEN 1 AND 12", name="ck_receipts_month"),
        CheckConstraint("version >= 1", name="ck_receipts_version"),
        CheckConstraint(
            f"size_bytes BETWEEN 1 AND {MAX_FILE_BYTES}", name="ck_receipts_size"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    unit_id: Mapped[UUID] = mapped_column(ForeignKey("units.id"))
    request_id: Mapped[UUID]
    billing_year: Mapped[int]
    billing_month: Mapped[int]
    version: Mapped[int]
    reason: Mapped[str] = mapped_column(String(500))
    issued_by_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    snapshot: Mapped[dict] = mapped_column(JSONB)
    filename: Mapped[str] = mapped_column(String(120))
    storage_key: Mapped[str] = mapped_column(String(160))
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
