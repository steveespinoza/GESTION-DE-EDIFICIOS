from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.properties.models import Building
from app.properties.schemas import BuildingDetail, BuildingInput, BuildingSummary


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
    statement = (
        update(Building)
        .where(Building.id == building_id)
        .values(**data.model_dump())
        .returning(Building)
    )
    building = db.scalar(statement)
    if building is None:
        return None
    detail = BuildingDetail.model_validate(building)
    db.commit()
    return detail
