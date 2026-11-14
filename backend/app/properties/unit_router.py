from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import RequestSession
from app.identity.models import RoleName
from app.identity.owners import list_available_owners
from app.identity.router import require_role, require_session_header
from app.identity.schemas import OwnerDetail, OwnerOption, OwnerProfile
from app.properties import unit_service
from app.properties.unit_schemas import UnitCreate, UnitDetail, UnitInput

router = APIRouter(
    prefix="/api/admin",
    tags=["Unidades"],
    dependencies=[Depends(require_role(RoleName.SUPERADMIN))],
)
UNITS = "/buildings/{building_id}/units"


def require_unit(unit: UnitDetail | None) -> UnitDetail:
    if unit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unidad no encontrada."
        )
    return unit


def building_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Edificio no encontrado."
    )


@router.get("/owners")
def read_owners(db: RequestSession) -> list[OwnerOption]:
    return list_available_owners(db)


@router.get(UNITS)
def read_units(
    building_id: UUID, db: RequestSession, q: Annotated[str, Query(max_length=150)] = ""
) -> list[UnitDetail]:
    units = unit_service.list_units(db, building_id, q.strip())
    if units is None:
        raise building_not_found()
    return units


@router.post(
    UNITS,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_session_header)],
)
def create_unit(building_id: UUID, data: UnitCreate, db: RequestSession) -> UnitDetail:
    unit = unit_service.create_unit(db, building_id, data)
    if unit is None:
        raise building_not_found()
    return unit


@router.get(UNITS + "/{unit_id}")
def read_unit(building_id: UUID, unit_id: UUID, db: RequestSession) -> UnitDetail:
    return require_unit(unit_service.find_unit(db, building_id, unit_id))


@router.put(UNITS + "/{unit_id}", dependencies=[Depends(require_session_header)])
def replace_unit(
    building_id: UUID, unit_id: UUID, data: UnitInput, db: RequestSession
) -> UnitDetail:
    return require_unit(unit_service.replace_unit(db, building_id, unit_id, data))


@router.put(UNITS + "/{unit_id}/owner", dependencies=[Depends(require_session_header)])
def replace_owner(
    building_id: UUID, unit_id: UUID, data: OwnerProfile, db: RequestSession
) -> OwnerDetail:
    owner = unit_service.replace_unit_owner(db, building_id, unit_id, data)
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Propietario de la unidad no encontrado.",
        )
    return owner
