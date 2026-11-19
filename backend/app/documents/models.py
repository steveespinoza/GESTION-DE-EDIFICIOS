from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
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


class ReceiptBatch(Base):
    __tablename__ = "receipt_batches"
    __table_args__ = (
        UniqueConstraint(
            "building_id", "request_id", name="uq_receipt_batches_request"
        ),
        CheckConstraint(
            "billing_year BETWEEN 2020 AND 9999", name="ck_receipt_batches_year"
        ),
        CheckConstraint(
            "billing_month BETWEEN 1 AND 12", name="ck_receipt_batches_month"
        ),
        CheckConstraint(
            "base_deadline_revision >= 0 AND deadline_revision >= 1",
            name="ck_receipt_batches_revision",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    building_id: Mapped[UUID] = mapped_column(ForeignKey("buildings.id"))
    request_id: Mapped[UUID]
    billing_year: Mapped[int]
    billing_month: Mapped[int]
    due_date: Mapped[date]
    deadline_id: Mapped[UUID] = mapped_column(ForeignKey("collection_deadlines.id"))
    base_deadline_revision: Mapped[int]
    deadline_revision: Mapped[int]
    reason: Mapped[str] = mapped_column(String(500))
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ReceiptBatchItem(Base):
    __tablename__ = "receipt_batch_items"
    __table_args__ = (
        UniqueConstraint("receipt_id", name="uq_receipt_batch_items_receipt"),
        CheckConstraint(
            "status IN ('PENDING','ISSUED','FAILED','SKIPPED')",
            name="ck_receipt_batch_items_status",
        ),
        CheckConstraint(
            "revision >= 0 AND attempts >= 0", name="ck_receipt_batch_items_counters"
        ),
        CheckConstraint(
            "(status = 'ISSUED') = (receipt_id IS NOT NULL)",
            name="ck_receipt_batch_items_receipt",
        ),
        CheckConstraint(
            "(status = 'FAILED') = (error_code IS NOT NULL) AND (status = 'FAILED') = (error_message IS NOT NULL)",
            name="ck_receipt_batch_items_error",
        ),
        CheckConstraint(
            "(attempts = 0) = (last_attempt_at IS NULL) AND (attempts = 0) = (last_attempt_by_id IS NULL)",
            name="ck_receipt_batch_items_attempt",
        ),
    )

    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("receipt_batches.id"), primary_key=True
    )
    unit_id: Mapped[UUID] = mapped_column(ForeignKey("units.id"), primary_key=True)
    unit_number: Mapped[str] = mapped_column(String(60))
    revision: Mapped[int]
    status: Mapped[str] = mapped_column(String(16))
    receipt_id: Mapped[UUID | None] = mapped_column(ForeignKey("receipts.id"))
    attempts: Mapped[int] = mapped_column(server_default="0")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("accounts.id"))
    error_code: Mapped[str | None] = mapped_column(String(16))
    error_message: Mapped[str | None] = mapped_column(String(250))
