from typing import Annotated
from urllib.parse import unquote
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from app.collections import reports
from app.collections.report_models import PaymentReport
from app.collections.report_schemas import RejectionInput, ReportDetail, ReportUpload
from app.collections.router import Admin, Owner
from app.collections.schemas import PaymentValues
from app.collections.service import PaymentConflict, UnitNotFound
from app.dependencies import RequestSession
from app.identity.router import require_session_header
from app.storage.files import InvalidAttachment, StorageUnavailable
from app.storage.http import StorageFactory, private_download, read_body

router = APIRouter(tags=["Reportes de pago"])
OWNER_REPORTS = "/api/owner/properties/{unit_id}/payment-reports"
BUILDING_REPORTS = "/api/admin/buildings/{building_id}/payment-reports"


@router.get(OWNER_REPORTS)
def owner_list(unit_id: UUID, db: RequestSession, user: Owner) -> list[ReportDetail]:
    try:
        return reports.owner_reports(db, unit_id, user.id)
    except UnitNotFound as error:
        raise HTTPException(404, "Unidad no encontrada.") from error


@router.post(
    OWNER_REPORTS, status_code=201, dependencies=[Depends(require_session_header)]
)
async def submit(
    unit_id: UUID,
    metadata: Annotated[str, Header(alias="X-Edificios-Report", max_length=4096)],
    request: Request,
    response: Response,
    db: RequestSession,
    user: Owner,
    storage: StorageFactory,
) -> ReportDetail:
    try:
        await run_in_threadpool(reports.owned_unit, db, unit_id, user.id)
        data = ReportUpload.model_validate_json(unquote(metadata, errors="strict"))
        body = await read_body(request)
        detail, created = await run_in_threadpool(
            reports.submit_report,
            db,
            unit_id,
            user.id,
            data,
            body,
            storage,
        )
    except UnitNotFound as error:
        raise HTTPException(404, "Unidad no encontrada.") from error
    except (ValidationError, UnicodeDecodeError) as error:
        raise HTTPException(422, "Revisa los datos del reporte de pago.") from error
    except InvalidAttachment as error:
        raise HTTPException(415, str(error)) from error
    except PaymentConflict as error:
        raise HTTPException(409, str(error)) from error
    except StorageUnavailable as error:
        raise HTTPException(503, str(error)) from error
    if not created:
        response.status_code = 200
    return detail


@router.get(BUILDING_REPORTS)
def building_list(
    building_id: UUID, db: RequestSession, _user: Admin
) -> list[ReportDetail]:
    try:
        return reports.building_reports(db, building_id)
    except reports.ReportNotFound as error:
        raise HTTPException(404, str(error)) from error


def download(report: PaymentReport, storage: StorageFactory) -> RedirectResponse:
    try:
        return private_download(
            storage().download_url(report.storage_key, report.filename)
        )
    except StorageUnavailable as error:
        raise HTTPException(503, str(error)) from error


@router.get(
    f"{OWNER_REPORTS}/{{report_id}}/proof",
    status_code=303,
    response_class=RedirectResponse,
)
def owner_download(
    unit_id: UUID,
    report_id: UUID,
    db: RequestSession,
    user: Owner,
    storage: StorageFactory,
) -> RedirectResponse:
    try:
        return download(reports.owner_proof(db, unit_id, report_id, user.id), storage)
    except reports.ReportNotFound as error:
        raise HTTPException(
            404, str(error), headers={"Cache-Control": "no-store"}
        ) from error


@router.get(
    f"{BUILDING_REPORTS}/{{report_id}}/proof",
    status_code=303,
    response_class=RedirectResponse,
)
def admin_download(
    building_id: UUID,
    report_id: UUID,
    db: RequestSession,
    _user: Admin,
    storage: StorageFactory,
) -> RedirectResponse:
    try:
        report, _ = reports.building_report(db, building_id, report_id)
        return download(report, storage)
    except reports.ReportNotFound as error:
        raise HTTPException(
            404, str(error), headers={"Cache-Control": "no-store"}
        ) from error


@router.put(
    f"{BUILDING_REPORTS}/{{report_id}}/approval",
    dependencies=[Depends(require_session_header)],
)
def approve(
    building_id: UUID,
    report_id: UUID,
    data: PaymentValues,
    db: RequestSession,
    user: Admin,
) -> ReportDetail:
    try:
        return reports.approve_report(db, building_id, report_id, user.id, data)
    except reports.ReportNotFound as error:
        raise HTTPException(404, str(error)) from error
    except PaymentConflict as error:
        raise HTTPException(409, str(error)) from error


@router.put(
    f"{BUILDING_REPORTS}/{{report_id}}/rejection",
    dependencies=[Depends(require_session_header)],
)
def reject(
    building_id: UUID,
    report_id: UUID,
    data: RejectionInput,
    db: RequestSession,
    user: Admin,
) -> ReportDetail:
    try:
        return reports.reject_report(db, building_id, report_id, user.id, data.reason)
    except reports.ReportNotFound as error:
        raise HTTPException(404, str(error)) from error
    except PaymentConflict as error:
        raise HTTPException(409, str(error)) from error
