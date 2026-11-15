from collections.abc import Callable
from datetime import datetime
from hashlib import sha256
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.attachment_models import FileKind, InvoiceAttachment
from app.billing.errors import InvoiceConflict, InvoiceNotFound
from app.billing.models import ServiceCategory, ServiceInvoice
from app.storage.files import FileStorage


class AttachmentDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: FileKind
    filename: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime


class InvalidAttachment(Exception):
    pass


def validate_attachment(filename: str, body: bytes) -> str:
    if not filename or any(
        character in "/\\" or ord(character) < 32 or ord(character) == 127
        for character in filename
    ):
        raise InvalidAttachment("El nombre del archivo no es válido.")
    extension = filename.rpartition(".")[2].lower()
    if extension == "pdf" and body.startswith(b"%PDF-"):
        return "application/pdf"
    if extension == "png" and body.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if extension in {"jpg", "jpeg"} and body.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    raise InvalidAttachment("Selecciona un archivo PDF, PNG o JPEG válido.")


def require_invoice(
    db: Session, building_id: UUID, invoice_id: UUID, *, lock: bool = False
) -> None:
    statement = (
        select(ServiceInvoice.id)
        .join(ServiceCategory, ServiceCategory.id == ServiceInvoice.category_id)
        .where(
            ServiceInvoice.id == invoice_id, ServiceCategory.building_id == building_id
        )
    )
    if lock:
        statement = statement.with_for_update(of=ServiceInvoice)
    if db.scalar(statement) is None:
        raise InvoiceNotFound("Factura no encontrada.")


def list_attachments(
    db: Session, building_id: UUID, invoice_id: UUID
) -> list[AttachmentDetail]:
    require_invoice(db, building_id, invoice_id)
    statement = (
        select(InvoiceAttachment)
        .where(InvoiceAttachment.invoice_id == invoice_id)
        .order_by(InvoiceAttachment.uploaded_at, InvoiceAttachment.id)
    )
    return [AttachmentDetail.model_validate(row) for row in db.scalars(statement)]


def attach_file(
    db: Session,
    building_id: UUID,
    invoice_id: UUID,
    kind: FileKind,
    filename: str,
    body: bytes,
    storage: Callable[[], FileStorage],
) -> tuple[AttachmentDetail, bool]:
    require_invoice(db, building_id, invoice_id, lock=True)
    filename = filename.strip()
    content_type = validate_attachment(filename, body)
    digest = sha256(body).hexdigest()
    file_kind = select(InvoiceAttachment).where(
        InvoiceAttachment.invoice_id == invoice_id, InvoiceAttachment.kind == kind
    )
    existing = db.scalar(file_kind.where(InvoiceAttachment.sha256 == digest))
    if existing is not None:
        return AttachmentDetail.model_validate(existing), False
    if kind == FileKind.VOUCHER and db.scalar(file_kind) is not None:
        raise InvoiceConflict("Esta factura ya tiene un comprobante del proveedor.")

    key = f"invoice-files/{invoice_id}/{kind.value.lower()}/{digest}"
    record = InvoiceAttachment(
        invoice_id=invoice_id,
        kind=kind,
        filename=filename,
        content_type=content_type,
        size_bytes=len(body),
        sha256=digest,
        storage_key=key,
    )
    try:
        db.add(record)
        db.flush()
        storage().put(key, body, content_type)
        detail = AttachmentDetail.model_validate(record)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return detail, True


def attachment_download(
    db: Session,
    building_id: UUID,
    invoice_id: UUID,
    attachment_id: UUID,
    storage: Callable[[], FileStorage],
) -> str:
    require_invoice(db, building_id, invoice_id)
    record = db.scalar(
        select(InvoiceAttachment).where(
            InvoiceAttachment.id == attachment_id,
            InvoiceAttachment.invoice_id == invoice_id,
        )
    )
    if record is None:
        raise InvoiceNotFound("Archivo no encontrado.")
    return storage().download_url(record.storage_key, record.filename)
