from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import RedirectResponse

from app.collections.deadlines import BuildingNotFound
from app.collections.router import Admin, Owner
from app.collections.service import UnitNotFound
from app.dependencies import RequestSession
from app.documents import service
from app.documents.consolidated_pdf import render_consolidation
from app.documents.consolidation import read_consolidation
from app.documents.excel import render_transparency
from app.documents.period import EmptyPeriod
from app.documents.schemas import ReceiptDetail, ReceiptInput
from app.documents.transparency import read_transparency
from app.identity.router import require_session_header
from app.storage.files import StorageUnavailable
from app.storage.http import StorageFactory, private_download

router = APIRouter(tags=["Recibos"])
ADMIN_RECEIPTS = "/api/admin/buildings/{building_id}/units/{unit_id}/receipts"
OWNER_RECEIPTS = "/api/owner/properties/{unit_id}/receipts"
Year = Annotated[int, Query(ge=2020, le=9999)]
Month = Annotated[int, Query(ge=1, le=12)]


@router.get("/api/admin/buildings/{building_id}/consolidation.pdf")
def admin_consolidation(
    building_id: UUID,
    billing_year: Year,
    billing_month: Month,
    db: RequestSession,
    _user: Admin,
) -> Response:
    try:
        report = read_consolidation(db, building_id, billing_year, billing_month)
    except BuildingNotFound as error:
        raise HTTPException(404, "Edificio no encontrado.") from error
    except EmptyPeriod as error:
        raise HTTPException(409, str(error)) from error
    return Response(
        content=render_consolidation(report),
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'attachment; filename="consolidado-{billing_year}-{billing_month:02}-{building_id.hex[:8]}.pdf"',
        },
    )


def transparency_download(db, unit_id, billing_year, billing_month, **scope):
    try:
        data = read_transparency(db, unit_id, billing_year, billing_month, **scope)
    except UnitNotFound as error:
        raise HTTPException(404, "Unidad no encontrada.") from error
    except EmptyPeriod as error:
        raise HTTPException(409, str(error)) from error
    return Response(
        content=render_transparency(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="transparencia-{billing_year}-{billing_month:02}-{unit_id.hex[:8]}.xlsx"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/api/admin/buildings/{building_id}/units/{unit_id}/transparency.xlsx")
def admin_transparency(
    building_id: UUID,
    unit_id: UUID,
    billing_year: Year,
    billing_month: Month,
    db: RequestSession,
    _user: Admin,
) -> Response:
    return transparency_download(
        db, unit_id, billing_year, billing_month, building_id=building_id
    )


@router.get("/api/owner/properties/{unit_id}/transparency.xlsx")
def owner_transparency(
    unit_id: UUID,
    billing_year: Year,
    billing_month: Month,
    db: RequestSession,
    user: Owner,
) -> Response:
    return transparency_download(
        db, unit_id, billing_year, billing_month, owner_id=user.id
    )


@router.get(ADMIN_RECEIPTS)
def admin_list(
    building_id: UUID, unit_id: UUID, db: RequestSession, _user: Admin
) -> list[ReceiptDetail]:
    try:
        return service.list_receipts(db, unit_id, building_id=building_id)
    except UnitNotFound as error:
        raise HTTPException(404, "Unidad no encontrada.") from error


@router.get(OWNER_RECEIPTS)
def owner_list(unit_id: UUID, db: RequestSession, user: Owner) -> list[ReceiptDetail]:
    try:
        return service.list_receipts(db, unit_id, owner_id=user.id)
    except UnitNotFound as error:
        raise HTTPException(404, "Unidad no encontrada.") from error


@router.post(
    ADMIN_RECEIPTS, status_code=201, dependencies=[Depends(require_session_header)]
)
def issue(
    building_id: UUID,
    unit_id: UUID,
    data: ReceiptInput,
    db: RequestSession,
    user: Admin,
    response: Response,
    storage: StorageFactory,
) -> ReceiptDetail:
    try:
        result, created = service.issue_receipt(
            db, building_id, unit_id, user.id, data, storage
        )
    except UnitNotFound as error:
        raise HTTPException(404, "Unidad no encontrada.") from error
    except service.ReceiptConflict as error:
        raise HTTPException(409, str(error)) from error
    except StorageUnavailable as error:
        raise HTTPException(503, str(error)) from error
    if not created:
        response.status_code = 200
    return result


def download(record, storage: StorageFactory) -> RedirectResponse:
    try:
        return private_download(
            storage().download_url(record.storage_key, record.filename)
        )
    except StorageUnavailable as error:
        raise HTTPException(503, str(error)) from error


@router.get(
    f"{ADMIN_RECEIPTS}/{{receipt_id}}/pdf",
    status_code=303,
    response_class=RedirectResponse,
)
def admin_download(
    building_id: UUID,
    unit_id: UUID,
    receipt_id: UUID,
    db: RequestSession,
    _user: Admin,
    storage: StorageFactory,
) -> RedirectResponse:
    try:
        record = service.find_receipt(db, unit_id, receipt_id, building_id=building_id)
    except (UnitNotFound, service.ReceiptNotFound) as error:
        raise HTTPException(404, "Recibo no encontrado.") from error
    return download(record, storage)


@router.get(
    f"{OWNER_RECEIPTS}/{{receipt_id}}/pdf",
    status_code=303,
    response_class=RedirectResponse,
)
def owner_download(
    unit_id: UUID,
    receipt_id: UUID,
    db: RequestSession,
    user: Owner,
    storage: StorageFactory,
) -> RedirectResponse:
    try:
        record = service.find_receipt(db, unit_id, receipt_id, owner_id=user.id)
    except (UnitNotFound, service.ReceiptNotFound) as error:
        raise HTTPException(404, "Recibo no encontrado.") from error
    return download(record, storage)
