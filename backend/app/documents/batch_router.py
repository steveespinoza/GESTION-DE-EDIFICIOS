from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from app.collections.deadlines import BuildingNotFound, DeadlineConflict
from app.collections.router import Admin
from app.dependencies import RequestSession
from app.documents import batches
from app.documents.batch_schemas import BatchDetail, BatchInput, BatchSummary
from app.identity.router import require_session_header
from app.storage.http import StorageFactory


def no_store(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(tags=["Lotes de recibos"], dependencies=[Depends(no_store)])
BASE = "/api/admin/buildings/{building_id}/receipt-batches"


@router.get(BASE)
def history(building_id: UUID, db: RequestSession, _user: Admin) -> list[BatchSummary]:
    try:
        return batches.list_batches(db, building_id)
    except BuildingNotFound as error:
        raise HTTPException(404, "Edificio no encontrado.") from error


@router.post(BASE, status_code=201, dependencies=[Depends(require_session_header)])
def prepare(
    building_id: UUID,
    data: BatchInput,
    db: RequestSession,
    user: Admin,
    response: Response,
) -> BatchDetail:
    try:
        result, created = batches.prepare_batch(db, building_id, user.id, data)
    except BuildingNotFound as error:
        raise HTTPException(404, "Edificio no encontrado.") from error
    except (batches.BatchConflict, DeadlineConflict) as error:
        raise HTTPException(409, str(error)) from error
    if not created:
        response.status_code = 200
    return result


@router.get(f"{BASE}/{{batch_id}}")
def read(
    building_id: UUID, batch_id: UUID, db: RequestSession, _user: Admin
) -> BatchDetail:
    try:
        return batches.read_batch(db, building_id, batch_id)
    except batches.BatchNotFound as error:
        raise HTTPException(404, "Lote no encontrado.") from error


@router.post(
    f"{BASE}/{{batch_id}}/items/{{unit_id}}/issue",
    dependencies=[Depends(require_session_header)],
)
def issue(
    building_id: UUID,
    batch_id: UUID,
    unit_id: UUID,
    db: RequestSession,
    user: Admin,
    storage: StorageFactory,
) -> BatchDetail:
    try:
        return batches.issue_item(db, building_id, batch_id, unit_id, user.id, storage)
    except (BuildingNotFound, batches.BatchNotFound) as error:
        raise HTTPException(404, "Lote o unidad no encontrados.") from error
