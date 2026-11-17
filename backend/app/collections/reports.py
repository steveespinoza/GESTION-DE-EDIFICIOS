from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collections.report_models import PaymentReport, ReportStatus
from app.collections.report_schemas import ApprovalInput, ReportDetail, ReportUpload
from app.collections.schemas import PaymentInput
from app.collections.service import (
    PaymentConflict,
    UnitNotFound,
    money,
    payment_details,
    stage_payment,
)
from app.properties.models import Building, Unit
from app.properties.service import lock_building
from app.storage.files import FileStorage, validate_attachment


class ReportNotFound(Exception):
    pass


def report_detail(report: PaymentReport, unit: Unit) -> ReportDetail:
    return ReportDetail(
        id=report.id,
        unit_id=unit.id,
        unit_number=unit.number,
        status=report.status,
        billing_year=report.billing_year,
        billing_month=report.billing_month,
        received_on=report.received_on,
        amount=money(report.amount_cents),
        reference=report.reference,
        filename=report.filename,
        submitted_at=report.submitted_at.astimezone(UTC),
        reviewed_at=report.reviewed_at.astimezone(UTC) if report.reviewed_at else None,
        payment_id=report.payment_id,
        rejection_reason=report.rejection_reason,
        proof_revision=report.proof_revision,
    )


def owned_unit(
    db: Session, unit_id: UUID, owner_id: UUID, *, lock: bool = False
) -> Unit:
    query = select(Unit).where(Unit.id == unit_id, Unit.owner_id == owner_id)
    if lock:
        query = query.with_for_update()
    unit = db.scalar(query)
    if unit is None:
        raise UnitNotFound
    return unit


def owner_reports(db: Session, unit_id: UUID, owner_id: UUID) -> list[ReportDetail]:
    unit = owned_unit(db, unit_id, owner_id)
    query = (
        select(PaymentReport)
        .where(
            PaymentReport.unit_id == unit.id,
            PaymentReport.submitted_by_id == owner_id,
        )
        .order_by(PaymentReport.submitted_at.desc(), PaymentReport.id)
    )
    return [report_detail(report, unit) for report in db.scalars(query)]


def building_report_rows(building_id: UUID):
    return (
        select(PaymentReport, Unit)
        .join(Unit, Unit.id == PaymentReport.unit_id)
        .where(
            Unit.building_id == building_id,
        )
    )


def building_reports(db: Session, building_id: UUID) -> list[ReportDetail]:
    if db.get(Building, building_id) is None:
        raise ReportNotFound("Edificio no encontrado.")
    query = building_report_rows(building_id).order_by(
        PaymentReport.submitted_at.desc(), PaymentReport.id
    )
    return [report_detail(report, unit) for report, unit in db.execute(query)]


def submit_report(
    db: Session,
    unit_id: UUID,
    owner_id: UUID,
    data: ReportUpload,
    body: bytes,
    storage: Callable[[], FileStorage],
) -> tuple[ReportDetail, bool]:
    unit = owned_unit(db, unit_id, owner_id, lock=True)
    content_type = validate_attachment(data.filename, body)
    digest = sha256(body).hexdigest()
    attributes = data.model_dump(exclude={"amount"}) | {
        "unit_id": unit.id,
        "submitted_by_id": owner_id,
        "amount_cents": int(data.amount.scaleb(2)),
        "digest": digest,
    }
    existing = db.scalar(
        select(PaymentReport).filter_by(unit_id=unit.id, request_id=data.request_id)
    )
    if existing is not None:
        if any(getattr(existing, key) != value for key, value in attributes.items()):
            raise PaymentConflict(
                "Esta solicitud se usó para otro reporte. Revisa el historial."
            )
        return report_detail(existing, unit), False
    key = f"payment-proofs/{unit.id}/{data.request_id}/{digest}"
    report = PaymentReport(**attributes, storage_key=key, size_bytes=len(body))
    db.add(report)
    db.flush()
    storage().put(key, body, content_type)
    result = report_detail(report, unit)
    db.commit()
    return result, True


def owner_proof(
    db: Session, unit_id: UUID, report_id: UUID, owner_id: UUID
) -> PaymentReport:
    report = db.scalar(
        select(PaymentReport)
        .join(Unit, Unit.id == PaymentReport.unit_id)
        .where(
            PaymentReport.id == report_id,
            Unit.id == unit_id,
            Unit.owner_id == owner_id,
            PaymentReport.submitted_by_id == owner_id,
        )
    )
    if report is None:
        raise ReportNotFound("Comprobante no encontrado.")
    return report


def building_report(
    db: Session, building_id: UUID, report_id: UUID, *, review: bool = False
) -> tuple[PaymentReport, Unit]:
    if review and lock_building(db, building_id) is None:
        raise ReportNotFound("Reporte no encontrado.")
    query = building_report_rows(building_id).where(PaymentReport.id == report_id)
    if review:
        query = query.with_for_update(of=PaymentReport).execution_options(
            populate_existing=True
        )
    row = db.execute(query).one_or_none()
    if row is None:
        raise ReportNotFound("Reporte no encontrado.")
    return row[0], row[1]


def approve_report(
    db: Session,
    building_id: UUID,
    report_id: UUID,
    reviewer_id: UUID,
    data: ApprovalInput,
) -> ReportDetail:
    report, unit = building_report(db, building_id, report_id, review=True)
    require_proof_revision(report, data.proof_revision)
    if report.payment_id is not None:
        payment = payment_details(db, unit.id, report.payment_id)[0]
        if (payment.amount, payment.received_on, payment.reference) != (
            data.amount,
            data.received_on,
            data.reference,
        ):
            raise PaymentConflict(
                "El reporte ya fue aprobado con otros datos. Revisa el pago registrado."
            )
        return report_detail(report, unit)
    if report.status == ReportStatus.REJECTED:
        raise PaymentConflict("El reporte ya fue rechazado.")

    payment, _ = stage_payment(
        db,
        report.unit_id,
        reviewer_id,
        PaymentInput(
            **data.model_dump(exclude={"proof_revision"}),
            request_id=uuid4(),
            billing_year=report.billing_year,
            billing_month=report.billing_month,
        ),
    )
    report.payment_id = payment.id
    report.reviewed_at = datetime.now(UTC)
    report.reviewed_by_id = reviewer_id
    result = report_detail(report, unit)
    db.commit()
    return result


def reject_report(
    db: Session,
    building_id: UUID,
    report_id: UUID,
    reviewer_id: UUID,
    reason: str,
    proof_revision: int = 0,
) -> ReportDetail:
    report, unit = building_report(db, building_id, report_id, review=True)
    require_proof_revision(report, proof_revision)
    if report.status == ReportStatus.REJECTED and report.rejection_reason == reason:
        return report_detail(report, unit)
    if report.status != ReportStatus.PENDING:
        raise PaymentConflict("El reporte ya fue revisado.")
    report.rejection_reason = reason
    report.reviewed_at = datetime.now(UTC)
    report.reviewed_by_id = reviewer_id
    result = report_detail(report, unit)
    db.commit()
    return result


def require_proof_revision(report: PaymentReport, revision: int) -> None:
    if report.proof_revision != revision:
        raise PaymentConflict(
            "El comprobante cambió. Actualiza el reporte y revisa la versión vigente."
        )
