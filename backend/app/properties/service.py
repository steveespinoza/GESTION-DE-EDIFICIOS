from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.properties.models import Building, Unit
from app.properties.schemas import BuildingDetail, BuildingInput, BuildingSummary


class PropertyConflict(Exception):
    pass


def lock_building(db: Session, building_id: UUID) -> Building | None:
    return db.scalar(
        select(Building).where(Building.id == building_id).with_for_update()
    )


def count_units(db: Session, building_id: UUID) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Unit)
            .where(Unit.building_id == building_id)
        )
        or 0
    )


def list_buildings(db: Session) -> list[BuildingSummary]:
    statement = select(Building).order_by(func.lower(Building.name), Building.id)
    return [
        BuildingSummary.model_validate(building) for building in db.scalars(statement)
    ]


def find_building(db: Session, building_id: UUID) -> BuildingDetail | None:
    building = db.get(Building, building_id)
    return BuildingDetail.model_validate(building) if building is not None else None


def create_building(db: Session, data: BuildingInput) -> BuildingDetail:
    building = Building(**data.model_dump())
    db.add(building)
    db.flush()
    detail = BuildingDetail.model_validate(building)
    db.commit()
    return detail


def replace_building(
    db: Session, building_id: UUID, data: BuildingInput
) -> BuildingDetail | None:
    building = lock_building(db, building_id)
    if building is None:
        return None
    if data.total_units < count_units(db, building_id):
        raise PropertyConflict(
            "La capacidad no puede ser menor que las unidades registradas."
        )
    for field, value in data.model_dump().items():
        setattr(building, field, value)
    detail = BuildingDetail.model_validate(building)
    db.commit()
    return detail
