from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse

from app.collections.router import Admin, Owner
from app.collections.service import UnitNotFound
from app.dependencies import RequestSession
from app.documents import service
from app.documents.schemas import ReceiptDetail, ReceiptInput
from app.identity.router import require_session_header
from app.storage.files import StorageUnavailable
from app.storage.http import StorageFactory, private_download

router = APIRouter(tags=["Recibos"])
ADMIN_RECEIPTS = "/api/admin/buildings/{building_id}/units/{unit_id}/receipts"
OWNER_RECEIPTS = "/api/owner/properties/{unit_id}/receipts"


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
