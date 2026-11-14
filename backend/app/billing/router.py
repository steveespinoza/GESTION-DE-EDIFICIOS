from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.billing import catalog
from app.billing.schemas import ServiceCategoryDetail, ServiceCategoryInput
from app.dependencies import RequestSession
from app.identity.models import RoleName
from app.identity.router import require_role, require_session_header

router = APIRouter(
    prefix="/api/admin/buildings/{building_id}/services",
    tags=["Servicios"],
    dependencies=[Depends(require_role(RoleName.SUPERADMIN))],
)


def building_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Edificio no encontrado."
    )


@router.get("")
def list_services(building_id: UUID, db: RequestSession) -> list[ServiceCategoryDetail]:
    categories = catalog.list_categories(db, building_id)
    if categories is None:
        raise building_not_found()
    return categories


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_session_header)],
)
def create_service(
    building_id: UUID, data: ServiceCategoryInput, db: RequestSession
) -> ServiceCategoryDetail:
    try:
        category = catalog.create_category(db, building_id, data)
    except catalog.ServiceNameConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un servicio con ese nombre en este edificio.",
        ) from error
    if category is None:
        raise building_not_found()
    return category
