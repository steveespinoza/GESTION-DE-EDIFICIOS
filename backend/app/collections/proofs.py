from collections.abc import Callable
from datetime import UTC
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collections.report_models import (
    PaymentReport,
    PaymentReportProof,
    ReportStatus,
)
from app.collections.report_schemas import ProofDetail, ProofUpload, ReportDetail
from app.collections.reports import (
    ReportNotFound,
    building_report,
    report_detail,
    require_proof_revision,
)
from app.collections.service import PaymentConflict
from app.identity.models import Account
from app.storage.files import FileStorage, validate_attachment


def proof_history(db: Session, report: PaymentReport) -> list[ProofDetail]:
    original_author = db.scalar(
        select(Account.username).where(Account.id == report.submitted_by_id)
    )
    history = [
        ProofDetail(
            revision=0,
            filename=report.filename,
            size_bytes=report.size_bytes,
            uploaded_by=original_author,
            uploaded_at=report.submitted_at.astimezone(UTC),
            reason=None,
        )
    ]
    rows = db.execute(
        select(PaymentReportProof, Account.username)
        .join(Account, Account.id == PaymentReportProof.uploaded_by_id)
        .where(PaymentReportProof.report_id == report.id)
        .order_by(PaymentReportProof.revision)
    )
    history.extend(
        ProofDetail(
            revision=proof.revision,
            filename=proof.filename,
            size_bytes=proof.size_bytes,
            uploaded_by=username,
            uploaded_at=proof.uploaded_at.astimezone(UTC),
            reason=proof.reason,
        )
        for proof, username in rows
    )
    return history


def proof_version(
    db: Session, report: PaymentReport, revision: int
) -> PaymentReport | PaymentReportProof:
    if revision == 0:
        return report
    proof = db.get(PaymentReportProof, (report.id, revision))
    if proof is None:
        raise ReportNotFound("Comprobante no encontrado.")
    return proof


def replace_proof(
    db: Session,
    building_id: UUID,
    report_id: UUID,
    user_id: UUID,
    data: ProofUpload,
    body: bytes,
    storage: Callable[[], FileStorage],
) -> tuple[ReportDetail, bool]:
    report, unit = building_report(db, building_id, report_id, review=True)
    content_type = validate_attachment(data.filename, body)
    digest = sha256(body).hexdigest()
    existing = db.scalar(
        select(PaymentReportProof).where(
            PaymentReportProof.report_id == report.id,
            PaymentReportProof.request_id == data.request_id,
        )
    )
    if existing is not None:
        if (
            existing.revision != data.proof_revision + 1
            or existing.digest != digest
            or existing.filename != data.filename
            or existing.reason != data.reason
            or existing.uploaded_by_id != user_id
        ):
            raise PaymentConflict("Esta solicitud ya se usó para otro reemplazo.")
        return report_detail(report, unit), False
    if report.status != ReportStatus.PENDING:
        raise PaymentConflict("El reemplazo requiere un reporte pendiente de revisión.")
    require_proof_revision(report, data.proof_revision)
    key = f"payment-proofs/{unit.id}/{report.id}/{data.request_id}/{digest}"
    proof = PaymentReportProof(
        report_id=report.id,
        revision=report.proof_revision + 1,
        request_id=data.request_id,
        uploaded_by_id=user_id,
        reason=data.reason,
        filename=data.filename,
        size_bytes=len(body),
        digest=digest,
        storage_key=key,
    )
    db.add(proof)
    db.flush()
    storage().put(key, body, content_type)
    report.proof_revision = proof.revision
    result = report_detail(report, unit)
    db.commit()
    return result, True
