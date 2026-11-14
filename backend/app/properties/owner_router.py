from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import RequestSession
from app.identity.models import RoleName
from app.identity.router import require_role
from app.identity.schemas import SessionUser
from app.properties import owner_service
from app.properties.owner_schemas import OwnerBuildingGroup, OwnerUnitDetail

router = APIRouter(prefix="/api/owner/properties", tags=["Mis propiedades"])
OwnerUser = Annotated[SessionUser, Depends(require_role(RoleName.OWNER))]


@router.get("")
def read_properties(owner: OwnerUser, db: RequestSession) -> list[OwnerBuildingGroup]:
    return owner_service.list_properties(db, owner.id)


@router.get("/{unit_id}")
def read_property(
    unit_id: UUID, owner: OwnerUser, db: RequestSession
) -> OwnerUnitDetail:
    detail = owner_service.find_property(db, owner.id, unit_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unidad no encontrada.",
            headers={"Cache-Control": "no-store"},
        )
    return detail
