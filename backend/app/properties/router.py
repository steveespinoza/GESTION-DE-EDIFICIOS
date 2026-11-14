from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import RequestSession
from app.identity.models import RoleName
from app.identity.router import require_role, require_session_header
from app.properties import service
from app.properties.schemas import BuildingDetail, BuildingInput, BuildingSummary

router = APIRouter(
    prefix="/api/admin/buildings",
    tags=["Edificios"],
    dependencies=[Depends(require_role(RoleName.SUPERADMIN))],
)


@router.get("")
def list_buildings(db: RequestSession) -> list[BuildingSummary]:
    return service.list_buildings(db)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_session_header)],
)
def create_building(data: BuildingInput, db: RequestSession) -> BuildingDetail:
    return service.create_building(db, data)


def require_building(building: BuildingDetail | None) -> BuildingDetail:
    if building is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Edificio no encontrado."
        )
    return building


@router.get("/{building_id}")
def read_building(building_id: UUID, db: RequestSession) -> BuildingDetail:
    return require_building(service.find_building(db, building_id))


@router.put("/{building_id}", dependencies=[Depends(require_session_header)])
def replace_building(
    building_id: UUID, data: BuildingInput, db: RequestSession
) -> BuildingDetail:
    return require_building(service.replace_building(db, building_id, data))
