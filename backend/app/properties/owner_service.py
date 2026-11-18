from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collections.ledger import unit_balance_cents, unit_credit_cents
from app.properties.models import Building, Unit
from app.properties.owner_schemas import (
    OwnerBuilding,
    OwnerBuildingGroup,
    OwnerUnitDetail,
    OwnerUnitSummary,
    PaymentInstructions,
)


def owned_units(owner_id: UUID):
    return (
        select(Unit, Building)
        .join(Building, Unit.building_id == Building.id)
        .where(Unit.owner_id == owner_id)
    )


def list_properties(db: Session, owner_id: UUID) -> list[OwnerBuildingGroup]:
    # One SQL snapshot includes both totals, even while a payment is being recorded.
    statement = (
        owned_units(owner_id)
        .add_columns(unit_balance_cents(), unit_credit_cents())
        .order_by(
            func.lower(Building.name), Building.id, func.lower(Unit.number), Unit.id
        )
    )
    groups: dict[UUID, OwnerBuildingGroup] = {}
    for unit, building, balance, credit in db.execute(statement):
        group = groups.get(building.id)
        if group is None:
            group = OwnerBuildingGroup.model_validate(building)
            groups[building.id] = group
        group.units.append(
            OwnerUnitSummary(
                id=unit.id,
                number=unit.number,
                area_sqm=unit.area_sqm,
                balance=Decimal(balance).scaleb(-2),
                credit=Decimal(credit).scaleb(-2),
            )
        )
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
