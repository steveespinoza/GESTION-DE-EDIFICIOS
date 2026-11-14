from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from uuid import UUID

from psycopg.errors import UniqueViolation
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.identity.models import Account, RoleName
from app.identity.owners import add_owner, find_available_owner
from app.identity.schemas import OwnerDetail, OwnerProfile
from app.properties.models import Building, Unit
from app.properties.service import PropertyConflict, count_units, lock_building
from app.properties.unit_schemas import ExistingOwner, UnitCreate, UnitDetail, UnitInput

CONFLICT_MESSAGES = {
    "uq_units_building_number": "Ya existe una unidad con ese número en este edificio.",
    "accounts_username_key": "El nombre de usuario ya está registrado.",
    "uq_accounts_email": "El correo electrónico ya está registrado.",
}


@contextmanager
def unit_transaction(db: Session) -> Iterator[None]:
    try:
        yield
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if isinstance(error.orig, UniqueViolation):
            message = CONFLICT_MESSAGES.get(error.orig.diag.constraint_name)
            if message:
                raise PropertyConflict(message) from error
        raise


def unit_detail(unit: Unit, owner: Account) -> UnitDetail:
    return UnitDetail(
        id=unit.id,
        building_id=unit.building_id,
        number=unit.number,
        area_sqm=unit.area_sqm.quantize(Decimal("0.01")),
        owner=OwnerDetail.model_validate(owner),
    )


def units_with_owners(building_id: UUID):
    return (
        select(Unit, Account)
        .join(Account, Unit.owner_id == Account.id)
        .where(Unit.building_id == building_id)
    )


def list_units(db: Session, building_id: UUID, query: str) -> list[UnitDetail] | None:
    if db.get(Building, building_id) is None:
        return None
    statement = units_with_owners(building_id)
    if query:
        statement = statement.where(
            or_(
                Unit.number.icontains(query, autoescape=True),
                Account.full_name.icontains(query, autoescape=True),
                Account.username.icontains(query, autoescape=True),
            )
        )
    rows = db.execute(statement.order_by(func.lower(Unit.number), Unit.id))
    return [unit_detail(unit, owner) for unit, owner in rows]


def find_unit(db: Session, building_id: UUID, unit_id: UUID) -> UnitDetail | None:
    record = db.execute(
        units_with_owners(building_id).where(Unit.id == unit_id)
    ).one_or_none()
    return unit_detail(*record) if record is not None else None


def create_unit(db: Session, building_id: UUID, data: UnitCreate) -> UnitDetail | None:
    with unit_transaction(db):
        # Capacity changes and unit creation serialize on this same building row.
        building = lock_building(db, building_id)
        if building is None:
            return None
        if count_units(db, building_id) >= building.total_units:
            raise PropertyConflict("El edificio alcanzó su capacidad de unidades.")

        selection = data.owner
        if isinstance(selection, ExistingOwner):
            owner = find_available_owner(db, selection.id)
            if owner is None:
                raise PropertyConflict(
                    "El propietario seleccionado no está disponible."
                )
        else:
            profile = OwnerProfile.model_validate(
                selection.model_dump(exclude={"kind", "password"})
            )
            owner = add_owner(db, profile, selection.password)
            db.flush()

        unit = Unit(
            building_id=building_id,
            owner_id=owner.id,
            number=data.number,
            area_sqm=data.area_sqm,
        )
        db.add(unit)
        db.flush()
        return unit_detail(unit, owner)


def replace_unit(
    db: Session, building_id: UUID, unit_id: UUID, data: UnitInput
) -> UnitDetail | None:
    with unit_transaction(db):
        unit = db.scalar(
            update(Unit)
            .where(Unit.id == unit_id, Unit.building_id == building_id)
            .values(**data.model_dump())
            .returning(Unit)
        )
        if unit is None:
            return None
        owner = db.scalars(select(Account).where(Account.id == unit.owner_id)).one()
        return unit_detail(unit, owner)


def replace_unit_owner(
    db: Session, building_id: UUID, unit_id: UUID, data: OwnerProfile
) -> OwnerDetail | None:
    with unit_transaction(db):
        linked_owner = select(Unit.owner_id).where(
            Unit.id == unit_id, Unit.building_id == building_id
        )
        owner = db.scalar(
            update(Account)
            .where(
                Account.id == linked_owner.scalar_subquery(),
                Account.role_name == RoleName.OWNER.value,
            )
            .values(**data.model_dump())
            .returning(Account)
        )
        return OwnerDetail.model_validate(owner) if owner is not None else None
