from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collections.deadline_schemas import CollectionOverview
from app.collections.ledger import unit_credit_cents
from app.collections.overview import read_overview
from app.collections.service import money
from app.documents.period import EmptyPeriod
from app.identity.models import Account
from app.properties.models import Unit


@dataclass(frozen=True)
class HistoryUnit:
    id: UUID
    number: str
    owner: str
    credit: Decimal


@dataclass(frozen=True)
class CollectionHistory:
    overview: CollectionOverview
    units: list[HistoryUnit]
    generated_at: datetime


def read_collection_history(db: Session, building_id: UUID) -> CollectionHistory:
    # The overview keeps the shared building lock until rendering finishes.
    overview = read_overview(db, building_id)
    if not overview.rows:
        raise EmptyPeriod("El edificio no tiene periodos con cargos para exportar.")
    units = [
        HistoryUnit(identifier, number, owner, money(credit))
        for identifier, number, owner, credit in db.execute(
            select(Unit.id, Unit.number, Account.full_name, unit_credit_cents())
            .join(Account, Account.id == Unit.owner_id)
            .where(Unit.building_id == building_id)
            .order_by(Unit.number, Unit.id)
        )
    ]
    return CollectionHistory(overview, units, datetime.now(UTC))
