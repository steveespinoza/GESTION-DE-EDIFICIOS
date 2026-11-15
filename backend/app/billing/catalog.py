from uuid import UUID

from psycopg.errors import UniqueViolation
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billing.models import SERVICE_NAME_INDEX, ServiceCategory
from app.billing.schemas import ServiceCategoryDetail, ServiceCategoryInput
from app.properties.models import Building


class ServiceNameConflict(Exception):
    pass


def building_exists(db: Session, building_id: UUID) -> bool:
    return db.scalar(select(Building.id).where(Building.id == building_id)) is not None


def list_categories(
    db: Session, building_id: UUID
) -> list[ServiceCategoryDetail] | None:
    if not building_exists(db, building_id):
        return None
    statement = (
        select(ServiceCategory)
        .where(ServiceCategory.building_id == building_id)
        .order_by(func.lower(ServiceCategory.name))
    )
    return [
        ServiceCategoryDetail.model_validate(category)
        for category in db.scalars(statement)
    ]


def create_category(
    db: Session, building_id: UUID, data: ServiceCategoryInput
) -> ServiceCategoryDetail | None:
    if not building_exists(db, building_id):
        return None
    category = ServiceCategory(
        building_id=building_id, name=data.name, calculation_type=data.calculation_type
    )
    try:
        db.add(category)
        db.flush()
        result = ServiceCategoryDetail.model_validate(category)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if (
            isinstance(error.orig, UniqueViolation)
            and error.orig.diag.constraint_name == SERVICE_NAME_INDEX
        ):
            raise ServiceNameConflict from error
        raise
    return result
