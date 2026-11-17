from datetime import date, datetime
from enum import StrEnum
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
from app.storage.files import MAX_FILE_BYTES


class ReportStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


REVIEW_STATE_CHECK = """
    (reviewed_at IS NULL AND reviewed_by_id IS NULL AND payment_id IS NULL AND rejection_reason IS NULL)
    OR (reviewed_at IS NOT NULL AND reviewed_by_id IS NOT NULL AND
        ((payment_id IS NOT NULL AND rejection_reason IS NULL)
         OR (payment_id IS NULL AND rejection_reason IS NOT NULL)))
"""


class PaymentReport(Base):
    __tablename__ = "payment_reports"
    __table_args__ = (
        UniqueConstraint(
            "unit_id", "request_id", name="uq_payment_reports_unit_request"
        ),
        UniqueConstraint("payment_id", name="uq_payment_reports_payment"),
        Index("ix_payment_reports_unit_submitted", "unit_id", "submitted_at"),
        CheckConstraint(
            "billing_year BETWEEN 2020 AND 9999", name="ck_payment_reports_year"
        ),
        CheckConstraint(
            "billing_month BETWEEN 1 AND 12", name="ck_payment_reports_month"
        ),
        CheckConstraint(
            "amount_cents BETWEEN 1 AND 999999999999", name="ck_payment_reports_amount"
        ),
        CheckConstraint(
            f"size_bytes BETWEEN 1 AND {MAX_FILE_BYTES}",
            name="ck_payment_reports_proof_size",
        ),
        CheckConstraint(REVIEW_STATE_CHECK, name="ck_payment_reports_state"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    unit_id: Mapped[UUID] = mapped_column(ForeignKey("units.id"))
    submitted_by_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"))
    request_id: Mapped[UUID]
    billing_year: Mapped[int]
    billing_month: Mapped[int]
    received_on: Mapped[date]
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    reference: Mapped[str | None] = mapped_column(String(120))
    filename: Mapped[str] = mapped_column(String(200))
    size_bytes: Mapped[int]
    digest: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(160))
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("accounts.id"))
    payment_id: Mapped[UUID | None] = mapped_column(ForeignKey("payments.id"))
    rejection_reason: Mapped[str | None] = mapped_column(String(500))

    @property
    def status(self) -> ReportStatus:
        if self.payment_id is not None:
            return ReportStatus.APPROVED
        if self.rejection_reason is not None:
            return ReportStatus.REJECTED
        return ReportStatus.PENDING
