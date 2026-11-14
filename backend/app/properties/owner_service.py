from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.properties.models import Building, Unit
from app.properties.owner_schemas import (
    OwnerBuilding,
    OwnerBuildingGroup,
    OwnerUnit,
    OwnerUnitDetail,
    PaymentInstructions,
)


def owned_units(owner_id: UUID):
    return (
        select(Unit, Building)
        .join(Building, Unit.building_id == Building.id)
        .where(Unit.owner_id == owner_id)
    )


def list_properties(db: Session, owner_id: UUID) -> list[OwnerBuildingGroup]:
    statement = owned_units(owner_id).order_by(
        func.lower(Building.name), Building.id, func.lower(Unit.number), Unit.id
    )
    groups: dict[UUID, OwnerBuildingGroup] = {}
    for unit, building in db.execute(statement):
        group = groups.get(building.id)
        if group is None:
            group = OwnerBuildingGroup.model_validate(building)
            groups[building.id] = group
        group.units.append(OwnerUnit.model_validate(unit))
    return list(groups.values())


def find_property(db: Session, owner_id: UUID, unit_id: UUID) -> OwnerUnitDetail | None:
    record = db.execute(owned_units(owner_id).where(Unit.id == unit_id)).one_or_none()
    if record is None:
        return None
    unit, building = record
    return OwnerUnitDetail(
        id=unit.id,
        number=unit.number,
        area_sqm=unit.area_sqm,
        building=OwnerBuilding.model_validate(building),
        payment_instructions=PaymentInstructions.model_validate(building),
    )
