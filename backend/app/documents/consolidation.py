from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.billing.invoice_schemas import AccountingPeriod
from app.billing.models import ServiceCategory, ServiceInvoice, UnitCharge
from app.collections import deadlines
from app.collections.ledger import (
    adjustment_cents,
    net_applied_cents,
    unit_credit_cents,
)
from app.collections.service import money
from app.documents.period import EmptyPeriod
from app.identity.models import Account
from app.properties.models import Building, Unit


class UnitAmounts(BaseModel):
    current_amount: Decimal = Decimal("0.00")
    current_applied: Decimal = Decimal("0.00")
    current_balance: Decimal = Decimal("0.00")
    previous_balance: Decimal = Decimal("0.00")
    overdue_balance: Decimal = Decimal("0.00")
    credit: Decimal = Decimal("0.00")

    @property
    def total_pending(self) -> Decimal:
        return self.current_balance + self.previous_balance


class ConsolidatedUnit(UnitAmounts):
    unit_id: UUID
    unit_number: str
    owner_name: str
    has_current_charges: bool = False


class ConsolidatedService(BaseModel):
    invoice_id: UUID
    service: str
    provider_amount: Decimal
    adjustment: Decimal = Decimal("0.00")
    amount: Decimal = Decimal("0.00")
    applied: Decimal = Decimal("0.00")
    balance: Decimal = Decimal("0.00")


class Consolidation(AccountingPeriod):
    building_name: str
    address: str | None
    as_of: date
    generated_at: datetime
    due_date: date | None
    units: list[ConsolidatedUnit] = Field(default_factory=list)
    services: list[ConsolidatedService] = Field(default_factory=list)

    @property
    def totals(self) -> UnitAmounts:
        return UnitAmounts(
            **{
                field: sum((getattr(unit, field) for unit in self.units), money(0))
                for field in UnitAmounts.model_fields
            }
        )


def read_consolidation(
    db: Session, building_id: UUID, year: int, month: int
) -> Consolidation:
    # Every writer in the building takes the exclusive form of this lock first.
    building = db.scalar(
        select(Building).where(Building.id == building_id).with_for_update(read=True)
    )
    if building is None:
        raise deadlines.BuildingNotFound
    as_of = deadlines.business_today()
    dates = deadlines.current_dates(deadlines.deadline_history(db, building_id))
    units = {
        unit.id: ConsolidatedUnit(
            unit_id=unit.id,
            unit_number=unit.number,
            owner_name=owner,
            credit=money(credit),
        )
        for unit, owner, credit in db.execute(
            select(Unit, Account.full_name, unit_credit_cents())
            .join(Account, Account.id == Unit.owner_id)
            .where(Unit.building_id == building_id)
            .order_by(Unit.number, Unit.id)
        )
    }
    services: dict[UUID, ConsolidatedService] = {}
    query = (
        select(
            UnitCharge,
            ServiceInvoice,
            ServiceCategory.name,
            adjustment_cents(),
            net_applied_cents(),
        )
        .join(Unit, Unit.id == UnitCharge.unit_id)
        .join(ServiceInvoice, ServiceInvoice.id == UnitCharge.invoice_id)
        .join(ServiceCategory, ServiceCategory.id == ServiceInvoice.category_id)
        .where(
            Unit.building_id == building_id,
            ServiceCategory.building_id == building_id,
            tuple_(ServiceInvoice.billing_year, ServiceInvoice.billing_month)
            <= (year, month),
        )
        .order_by(ServiceCategory.name, ServiceInvoice.id, Unit.number, Unit.id)
    )
    for charge, invoice, service, adjustment, applied in db.execute(query):
        row = units[charge.unit_id]
        amount, applied_amount = money(charge.amount_cents + adjustment), money(applied)
        balance = amount - applied_amount
        current = (invoice.billing_year, invoice.billing_month) == (year, month)
        if current:
            row.has_current_charges = True
            row.current_amount += amount
            row.current_applied += applied_amount
            row.current_balance += balance
            if invoice.id not in services:
                services[invoice.id] = ConsolidatedService(
                    invoice_id=invoice.id,
                    service=service,
                    provider_amount=money(invoice.total_cents),
                )
            summary = services[invoice.id]
            summary.adjustment += money(adjustment)
            summary.amount += amount
            summary.applied += applied_amount
            summary.balance += balance
        else:
            row.previous_balance += balance
        if deadlines.is_overdue(
            balance, dates.get((invoice.billing_year, invoice.billing_month)), as_of
        ):
            row.overdue_balance += balance
    if not services:
        raise EmptyPeriod("El periodo seleccionado no tiene cargos en este edificio.")
    return Consolidation(
        billing_year=year,
        billing_month=month,
        building_name=building.name,
        address=building.address,
        as_of=as_of,
        generated_at=datetime.now(UTC),
        due_date=dates.get((year, month)),
        units=list(units.values()),
        services=list(services.values()),
    )
