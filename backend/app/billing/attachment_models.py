from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.storage.files import MAX_FILE_BYTES


class FileKind(StrEnum):
    DOCUMENT = "DOCUMENT"
    VOUCHER = "VOUCHER"


class InvoiceAttachment(Base):
    __tablename__ = "invoice_attachments"
    __table_args__ = (
        UniqueConstraint(
            "invoice_id", "kind", "sha256", name="uq_invoice_attachments_digest"
        ),
        Index(
            "uq_invoice_attachments_voucher",
            "invoice_id",
            unique=True,
            postgresql_where=text("kind = 'VOUCHER'"),
        ),
        CheckConstraint(
            f"size_bytes BETWEEN 1 AND {MAX_FILE_BYTES}",
            name="ck_invoice_attachments_size",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("service_invoices.id"))
    kind: Mapped[FileKind] = mapped_column(
        Enum(
            FileKind,
            name="ck_invoice_attachments_kind",
            native_enum=False,
            create_constraint=True,
        )
    )
    filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(32))
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(160))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
