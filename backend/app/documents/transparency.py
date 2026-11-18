from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.billing.models import MeterReading, ServiceInvoice, UnitCharge
from app.collections.schemas import Statement
from app.collections.service import read_statement
from app.documents.period import period_charges


@dataclass(frozen=True)
class Repartition:
    charge: UnitCharge
    invoice: ServiceInvoice
    unit_count: int
    total_consumption_milli: int
    previous_milli: int | None
    current_milli: int | None


@dataclass(frozen=True)
class Transparency:
    statement: Statement
    year: int
    month: int
    repartitions: list[Repartition]


def read_transparency(
    db: Session,
    unit_id: UUID,
    year: int,
    month: int,
    *,
    building_id: UUID | None = None,
    owner_id: UUID | None = None,
) -> Transparency:
    # The statement acquires the building's shared lock until the request ends.
    statement = read_statement(db, unit_id, building_id=building_id, owner_id=owner_id)
    current, _ = period_charges(statement, year, month)
    charge_count = (
        select(func.count())
        .select_from(UnitCharge)
        .where(UnitCharge.invoice_id == ServiceInvoice.id)
        .correlate(ServiceInvoice)
        .scalar_subquery()
    )
    consumption = (
        select(func.coalesce(func.sum(MeterReading.consumption_milli), 0))
        .where(MeterReading.invoice_id == ServiceInvoice.id)
        .correlate(ServiceInvoice)
        .scalar_subquery()
    )
    rows = db.execute(
        select(
            UnitCharge,
            ServiceInvoice,
            charge_count,
            consumption,
            MeterReading.previous_milli,
            MeterReading.current_milli,
        )
        .join(ServiceInvoice, ServiceInvoice.id == UnitCharge.invoice_id)
        .outerjoin(
            MeterReading,
            and_(
                MeterReading.invoice_id == ServiceInvoice.id,
                MeterReading.unit_id == UnitCharge.unit_id,
            ),
        )
        .where(UnitCharge.id.in_([c.id for c in current]))
        .order_by(ServiceInvoice.end_date, ServiceInvoice.id)
    )
    return Transparency(statement, year, month, [Repartition(*row) for row in rows])
