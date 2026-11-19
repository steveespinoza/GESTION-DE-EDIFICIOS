from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.billing.metering import from_milli
from app.billing.models import MeterReading, UnitCharge
from app.collections.service import (
    UnitNotFound,
    money,
    read_statement,
    unit_in_building,
)
from app.documents.models import Receipt
from app.documents.pdf import render_receipt
from app.documents.period import EmptyPeriod, period_charges
from app.documents.schemas import (
    ReceiptCharge,
    ReceiptDetail,
    ReceiptInput,
    ReceiptPayment,
    ReceiptSnapshot,
)
from app.identity.models import Account
from app.properties.models import Building, Unit
from app.properties.owner_schemas import PaymentInstructions
from app.properties.service import lock_building
from app.storage.files import MAX_FILE_BYTES, FileStorage


class ReceiptConflict(Exception):
    pass


class ReceiptNotFound(Exception):
    pass


def require_unit(
    db: Session,
    unit_id: UUID,
    *,
    building_id: UUID | None = None,
    owner_id: UUID | None = None,
) -> Unit:
    unit = db.scalar(
        select(Unit).where(
            Unit.id == unit_id,
            Unit.building_id == building_id
            if building_id is not None
            else Unit.owner_id == owner_id,
        )
    )
    if unit is None:
        raise UnitNotFound
    return unit


def detail(record: Receipt) -> ReceiptDetail:
    snapshot = ReceiptSnapshot.model_validate(record.snapshot)
    return ReceiptDetail(
        id=record.id,
        billing_year=record.billing_year,
        billing_month=record.billing_month,
        version=record.version,
        issued_at=record.issued_at.astimezone(UTC),
        issued_by=snapshot.issued_by,
        reason=record.reason,
        due_date=snapshot.due_date,
        total_pending=snapshot.total_pending,
        credit=snapshot.credit,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
    )


def list_receipts(
    db: Session,
    unit_id: UUID,
    *,
    building_id: UUID | None = None,
    owner_id: UUID | None = None,
) -> list[ReceiptDetail]:
    require_unit(db, unit_id, building_id=building_id, owner_id=owner_id)
    return [
        detail(record)
        for record in db.scalars(
            select(Receipt)
            .where(Receipt.unit_id == unit_id)
            .order_by(
                Receipt.billing_year.desc(),
                Receipt.billing_month.desc(),
                Receipt.version.desc(),
            )
        )
    ]


def find_receipt(
    db: Session,
    unit_id: UUID,
    receipt_id: UUID,
    *,
    building_id: UUID | None = None,
    owner_id: UUID | None = None,
) -> Receipt:
    require_unit(db, unit_id, building_id=building_id, owner_id=owner_id)
    record = db.scalar(
        select(Receipt).where(Receipt.unit_id == unit_id, Receipt.id == receipt_id)
    )
    if record is None:
        raise ReceiptNotFound
    return record


def capture(
    db: Session,
    building: Building,
    unit: Unit,
    actor_id: UUID,
    data: ReceiptInput,
    receipt_id: UUID,
    issued_at: datetime,
) -> ReceiptSnapshot:
    statement = read_statement(db, unit.id, building_id=building.id)
    period = (data.billing_year, data.billing_month)
    through_period = lambda item: (item.billing_year, item.billing_month) <= period
    try:
        current_charges, earlier_charges = period_charges(statement, *period)
    except EmptyPeriod as error:
        raise ReceiptConflict(str(error)) from error
    readings = {
        charge_id: (previous, current, common)
        for charge_id, previous, current, common in db.execute(
            select(
                UnitCharge.id,
                MeterReading.previous_milli,
                MeterReading.current_milli,
                UnitCharge.common_cents,
            )
            .outerjoin(
                MeterReading,
                and_(
                    MeterReading.invoice_id == UnitCharge.invoice_id,
                    MeterReading.unit_id == UnitCharge.unit_id,
                ),
            )
            .where(UnitCharge.unit_id == unit.id)
        )
    }

    def charge_snapshot(charge):
        previous, current, common = readings[charge.id]
        return ReceiptCharge(
            **charge.model_dump(),
            previous_reading=from_milli(previous) if previous is not None else None,
            current_reading=from_milli(current) if current is not None else None,
            original_common_amount=money(common) if common is not None else None,
        )

    charges = [charge_snapshot(c) for c in current_charges]
    earlier = [charge_snapshot(c) for c in earlier_charges]
    payments = []
    for payment in statement.payments:
        applied = sum(
            (
                application.net_amount
                for application in payment.applications
                if through_period(application)
            ),
            money(0),
        )
        if applied > 0:
            payments.append(
                ReceiptPayment(
                    id=payment.id,
                    received_on=payment.received_on,
                    amount=payment.amount,
                    applied=applied,
                    reference=payment.reference,
                )
            )
    current_balance = sum((c.balance for c in charges), money(0))
    previous_balance = sum((c.balance for c in earlier), money(0))
    return ReceiptSnapshot(
        receipt_id=receipt_id,
        version=data.revision + 1,
        billing_year=data.billing_year,
        billing_month=data.billing_month,
        issued_at=issued_at,
        issued_by=db.get(Account, actor_id).username,
        reason=data.reason,
        building_name=building.name,
        address=building.address,
        unit_number=unit.number,
        area_sqm=unit.area_sqm,
        owner_name=db.get(Account, unit.owner_id).full_name,
        due_date=charges[0].due_date,
        charges=charges,
        previous_charges=earlier,
        payments=payments,
        current_amount=sum((c.amount for c in charges), money(0)),
        current_applied=sum((c.applied for c in charges), money(0)),
        current_balance=current_balance,
        previous_balance=previous_balance,
        total_pending=current_balance + previous_balance,
        overdue_balance=sum(
            (c.balance for c in charges + earlier if c.overdue), money(0)
        ),
        credit=statement.credit,
        payment_instructions=PaymentInstructions.model_validate(building),
    )


def issue_receipt(
    db: Session,
    building_id: UUID,
    unit_id: UUID,
    actor_id: UUID,
    data: ReceiptInput,
    storage: Callable[[], FileStorage],
) -> tuple[ReceiptDetail, bool]:
    building = lock_building(db, building_id)
    if building is None:
        raise UnitNotFound
    unit = unit_in_building(db, building_id, unit_id)
    try:
        result, created = stage_receipt(db, building, unit, actor_id, data, storage)
        if created:
            db.commit()
    except Exception:
        db.rollback()
        raise
    return result, created


def stage_receipt(
    db: Session,
    building: Building,
    unit: Unit,
    actor_id: UUID,
    data: ReceiptInput,
    storage: Callable[[], FileStorage],
) -> tuple[ReceiptDetail, bool]:
    """Caller holds the exclusive building lock; receipt and result commit together."""
    unit_id = unit.id
    existing = db.scalar(
        select(Receipt).where(
            Receipt.unit_id == unit_id, Receipt.request_id == data.request_id
        )
    )
    if existing is not None:
        if (
            existing.billing_year,
            existing.billing_month,
            existing.version,
            existing.reason,
        ) != (data.billing_year, data.billing_month, data.revision + 1, data.reason):
            raise ReceiptConflict("La solicitud ya se utilizó con otros datos.")
        return detail(existing), False
    latest = (
        db.scalar(
            select(func.max(Receipt.version)).where(
                Receipt.unit_id == unit_id,
                Receipt.billing_year == data.billing_year,
                Receipt.billing_month == data.billing_month,
            )
        )
        or 0
    )
    if latest != data.revision:
        raise ReceiptConflict(
            "El recibo cambió. Actualiza el historial antes de emitir otra versión."
        )
    identifier, issued_at = uuid4(), datetime.now(UTC)
    snapshot = capture(db, building, unit, actor_id, data, identifier, issued_at)
    body = render_receipt(snapshot)
    if not 0 < len(body) <= MAX_FILE_BYTES:
        raise ReceiptConflict("El recibo supera el tamaño permitido.")
    record = Receipt(
        id=identifier,
        unit_id=unit_id,
        request_id=data.request_id,
        billing_year=data.billing_year,
        billing_month=data.billing_month,
        version=latest + 1,
        reason=data.reason,
        issued_by_id=actor_id,
        issued_at=issued_at,
        snapshot=snapshot.model_dump(mode="json"),
        filename=f"recibo-{data.billing_year}-{data.billing_month:02}-v{latest + 1}-{identifier.hex[:8]}.pdf",
        storage_key=f"receipts/{unit_id}/{identifier}.pdf",
        size_bytes=len(body),
        sha256=sha256(body).hexdigest(),
    )
    db.add(record)
    db.flush()
    storage().put(record.storage_key, body, "application/pdf")
    return detail(record), True
