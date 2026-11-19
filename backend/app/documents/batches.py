import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid5

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.billing.models import ServiceInvoice, UnitCharge
from app.collections import deadlines
from app.collections.deadline_schemas import DeadlineInput
from app.collections.service import UnitNotFound, unit_in_building
from app.documents.batch_schemas import (
    BatchDetail,
    BatchInput,
    BatchItemDetail,
    BatchSummary,
)
from app.documents.models import Receipt, ReceiptBatch, ReceiptBatchItem
from app.documents.schemas import ReceiptInput
from app.documents.service import ReceiptConflict, detail, stage_receipt
from app.identity.models import Account
from app.properties.models import Building, Unit
from app.properties.service import lock_building
from app.storage.files import FileStorage, StorageUnavailable

logger = logging.getLogger(__name__)


class BatchConflict(Exception):
    pass


class BatchNotFound(Exception):
    pass


def summary(batch: ReceiptBatch, actor: str, counts: dict[str, int]) -> BatchSummary:
    return BatchSummary(
        id=batch.id,
        billing_year=batch.billing_year,
        billing_month=batch.billing_month,
        due_date=batch.due_date,
        deadline_revision=batch.deadline_revision,
        reason=batch.reason,
        created_at=batch.created_at.astimezone(UTC),
        created_by=actor,
        pending=counts.get("PENDING", 0),
        issued=counts.get("ISSUED", 0),
        failed=counts.get("FAILED", 0),
        skipped=counts.get("SKIPPED", 0),
    )


def list_batches(db: Session, building_id: UUID) -> list[BatchSummary]:
    if db.scalar(select(Building.id).where(Building.id == building_id)) is None:
        raise deadlines.BuildingNotFound
    statuses = ("PENDING", "ISSUED", "FAILED", "SKIPPED")
    query = (
        select(
            ReceiptBatch,
            Account.username,
            *[
                func.count(ReceiptBatchItem.unit_id).filter(
                    ReceiptBatchItem.status == status
                )
                for status in statuses
            ],
        )
        .join(Account, Account.id == ReceiptBatch.created_by_id)
        .outerjoin(ReceiptBatchItem, ReceiptBatchItem.batch_id == ReceiptBatch.id)
        .where(ReceiptBatch.building_id == building_id)
        .group_by(ReceiptBatch.id, Account.username)
        .order_by(ReceiptBatch.created_at.desc(), ReceiptBatch.id.desc())
    )
    return [
        summary(row[0], row[1], dict(zip(statuses, row[2:], strict=True)))
        for row in db.execute(query)
    ]


def require_batch(db: Session, building_id: UUID, batch_id: UUID) -> ReceiptBatch:
    batch = db.scalar(
        select(ReceiptBatch).where(
            ReceiptBatch.id == batch_id, ReceiptBatch.building_id == building_id
        )
    )
    if batch is None:
        raise BatchNotFound
    return batch


def read_batch(db: Session, building_id: UUID, batch_id: UUID) -> BatchDetail:
    batch = require_batch(db, building_id, batch_id)
    rows = db.execute(
        select(ReceiptBatchItem, Receipt, Account.username)
        .outerjoin(Receipt, Receipt.id == ReceiptBatchItem.receipt_id)
        .outerjoin(Account, Account.id == ReceiptBatchItem.last_attempt_by_id)
        .where(ReceiptBatchItem.batch_id == batch.id)
        .order_by(ReceiptBatchItem.unit_number, ReceiptBatchItem.unit_id)
    )
    items = []
    counts: dict[str, int] = {}
    for item, receipt, actor in rows:
        counts[item.status] = counts.get(item.status, 0) + 1
        items.append(
            BatchItemDetail(
                unit_id=item.unit_id,
                unit_number=item.unit_number,
                revision=item.revision,
                status=item.status,
                attempts=item.attempts,
                last_attempt_at=item.last_attempt_at.astimezone(UTC)
                if item.last_attempt_at
                else None,
                last_attempt_by=actor,
                error_code=item.error_code,
                error_message=item.error_message,
                retryable=item.status == "FAILED"
                and item.error_code in ("STORAGE", "GENERATION"),
                receipt=detail(receipt) if receipt is not None else None,
            )
        )
    return BatchDetail(
        **summary(
            batch, db.get(Account, batch.created_by_id).username, counts
        ).model_dump(),
        items=items,
    )


def prepare_batch(
    db: Session, building_id: UUID, actor_id: UUID, data: BatchInput
) -> tuple[BatchDetail, bool]:
    if lock_building(db, building_id) is None:
        raise deadlines.BuildingNotFound
    existing = db.scalar(
        select(ReceiptBatch).where(
            ReceiptBatch.building_id == building_id,
            ReceiptBatch.request_id == data.request_id,
        )
    )
    if existing is not None:
        if (
            existing.billing_year,
            existing.billing_month,
            existing.due_date,
            existing.base_deadline_revision,
            existing.reason,
        ) != (
            data.billing_year,
            data.billing_month,
            data.due_date,
            data.deadline_revision,
            data.reason,
        ):
            raise BatchConflict("La solicitud ya se utilizó con otros datos.")
        return read_batch(db, building_id, existing.id), False
    current = next(
        (
            d
            for d in deadlines.deadline_history(db, building_id)
            if (d.billing_year, d.billing_month)
            == (data.billing_year, data.billing_month)
        ),
        None,
    )
    if data.deadline_revision != (current.revision if current else 0):
        raise BatchConflict(
            "El vencimiento cambió. Actualiza los datos antes de preparar el lote."
        )
    has_charges = (
        select(UnitCharge.id)
        .join(ServiceInvoice, ServiceInvoice.id == UnitCharge.invoice_id)
        .where(
            UnitCharge.unit_id == Unit.id,
            ServiceInvoice.billing_year == data.billing_year,
            ServiceInvoice.billing_month == data.billing_month,
        )
        .correlate(Unit)
        .exists()
    )
    latest_receipt = (
        select(func.coalesce(func.max(Receipt.version), 0))
        .where(
            Receipt.unit_id == Unit.id,
            Receipt.billing_year == data.billing_year,
            Receipt.billing_month == data.billing_month,
        )
        .correlate(Unit)
        .scalar_subquery()
    )
    cohort = db.execute(
        select(Unit, has_charges, latest_receipt)
        .where(Unit.building_id == building_id)
        .order_by(Unit.number, Unit.id)
    ).all()
    if not any(charged for _, charged, _ in cohort):
        raise BatchConflict("El periodo seleccionado no tiene cargos en este edificio.")
    identifier = uuid4()
    if current is None or current.due_date != data.due_date:
        current, _ = deadlines.stage_deadline(
            db,
            building_id,
            actor_id,
            DeadlineInput(
                billing_year=data.billing_year,
                billing_month=data.billing_month,
                request_id=uuid5(identifier, "deadline"),
                revision=data.deadline_revision,
                due_date=data.due_date,
                reason=data.reason,
            ),
        )
    batch = ReceiptBatch(
        id=identifier,
        building_id=building_id,
        request_id=data.request_id,
        billing_year=data.billing_year,
        billing_month=data.billing_month,
        due_date=data.due_date,
        base_deadline_revision=data.deadline_revision,
        deadline_id=current.id,
        deadline_revision=current.revision,
        reason=data.reason,
        created_by_id=actor_id,
    )
    try:
        db.add(batch)
        db.flush()
        db.add_all(
            ReceiptBatchItem(
                batch_id=identifier,
                unit_id=unit.id,
                unit_number=unit.number,
                revision=revision,
                status="PENDING" if charged else "SKIPPED",
                attempts=0,
            )
            for unit, charged, revision in cohort
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return read_batch(db, building_id, identifier), True


def issue_item(
    db: Session,
    building_id: UUID,
    batch_id: UUID,
    unit_id: UUID,
    actor_id: UUID,
    storage: Callable[[], FileStorage],
) -> BatchDetail:
    building = lock_building(db, building_id)
    if building is None:
        raise deadlines.BuildingNotFound
    batch = require_batch(db, building_id, batch_id)
    item = db.get(ReceiptBatchItem, (batch_id, unit_id))
    if item is None:
        raise BatchNotFound
    if item.status in ("ISSUED", "SKIPPED") or (
        item.status == "FAILED" and item.error_code not in ("STORAGE", "GENERATION")
    ):
        return read_batch(db, building_id, batch_id)
    item.attempts += 1
    item.last_attempt_at = datetime.now(UTC)
    item.last_attempt_by_id = actor_id
    try:
        with db.begin_nested():
            current = next(
                (
                    d
                    for d in deadlines.deadline_history(db, building_id)
                    if (d.billing_year, d.billing_month)
                    == (batch.billing_year, batch.billing_month)
                ),
                None,
            )
            if current is None or (current.id, current.revision, current.due_date) != (
                batch.deadline_id,
                batch.deadline_revision,
                batch.due_date,
            ):
                raise BatchConflict(
                    "El vencimiento cambió. Prepara otro lote con los datos actuales."
                )
            unit = unit_in_building(db, building_id, unit_id)
            receipt, _ = stage_receipt(
                db,
                building,
                unit,
                actor_id,
                ReceiptInput(
                    request_id=uuid5(batch.id, str(unit.id)),
                    revision=item.revision,
                    billing_year=batch.billing_year,
                    billing_month=batch.billing_month,
                    reason=batch.reason,
                ),
                storage,
            )
            item.receipt_id = receipt.id
            item.status = "ISSUED"
            item.error_code = item.error_message = None
    except (BatchConflict, ReceiptConflict) as error:
        item.status, item.error_code, item.error_message = (
            "FAILED",
            "CONFLICT",
            str(error),
        )
    except UnitNotFound:
        item.status, item.error_code, item.error_message = (
            "FAILED",
            "CHANGED",
            "La unidad ya no pertenece al edificio. Prepara otro lote.",
        )
    except StorageUnavailable:
        item.status, item.error_code, item.error_message = (
            "FAILED",
            "STORAGE",
            "No se pudo guardar el PDF. Puedes reintentar esta unidad.",
        )
    except SQLAlchemyError:
        raise
    except Exception:
        logger.exception(
            "Receipt batch generation failed for item %s/%s", batch_id, unit_id
        )
        item.status, item.error_code, item.error_message = (
            "FAILED",
            "GENERATION",
            "No se pudo generar el PDF. Puedes reintentar esta unidad.",
        )
    db.commit()
    return read_batch(db, building_id, batch_id)
