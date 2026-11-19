from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.billing.models import MeterReading, ServiceCategory, ServiceInvoice, UnitCharge
from app.collections.ledger import adjustment_cents, net_applied_cents
from app.documents.consolidation import Consolidation, read_consolidation
from app.properties.models import Unit


@dataclass(frozen=True)
class MonthlyCharge:
    charge: UnitCharge
    invoice: ServiceInvoice
    reading: MeterReading | None
    adjustment: int
    applied: int


@dataclass(frozen=True)
class MonthlyReport:
    summary: Consolidation
    charges: list[MonthlyCharge]


def read_monthly(
    db: Session, building_id: UUID, year: int, month: int
) -> MonthlyReport:
    # Consolidation holds the shared building lock through this read and rendering.
    summary = read_consolidation(db, building_id, year, month)
    rows = db.execute(
        select(
            UnitCharge,
            ServiceInvoice,
            MeterReading,
            adjustment_cents(),
            net_applied_cents(),
        )
        .join(Unit, Unit.id == UnitCharge.unit_id)
        .join(ServiceInvoice, ServiceInvoice.id == UnitCharge.invoice_id)
        .join(ServiceCategory, ServiceCategory.id == ServiceInvoice.category_id)
        .outerjoin(
            MeterReading,
            and_(
                MeterReading.invoice_id == UnitCharge.invoice_id,
                MeterReading.unit_id == UnitCharge.unit_id,
            ),
        )
        .where(
            Unit.building_id == building_id,
            ServiceCategory.building_id == building_id,
            ServiceInvoice.billing_year == year,
            ServiceInvoice.billing_month == month,
        )
        .order_by(ServiceCategory.name, ServiceInvoice.id, Unit.number, Unit.id)
    )
    return MonthlyReport(summary, [MonthlyCharge(*row) for row in rows])
