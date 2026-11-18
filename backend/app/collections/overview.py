from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.models import ServiceCategory, ServiceInvoice, UnitCharge
from app.collections import deadlines
from app.collections.deadline_schemas import CollectionOverview, CollectionRow
from app.collections.ledger import adjustment_cents, net_applied_cents
from app.identity.models import Account
from app.properties.models import Building, Unit


def read_overview(db: Session, building_id: UUID) -> CollectionOverview:
    building = db.scalar(
        select(Building).where(Building.id == building_id).with_for_update(read=True)
    )
    if building is None:
        raise deadlines.BuildingNotFound
    as_of = deadlines.business_today()
    history = deadlines.deadline_history(db, building_id)
    dates = deadlines.current_dates(history)
    rows = {}
    query = (
        select(
            Unit,
            Account.full_name,
            ServiceInvoice.billing_year,
            ServiceInvoice.billing_month,
            UnitCharge.amount_cents + adjustment_cents(),
            net_applied_cents(),
        )
        .join(UnitCharge, UnitCharge.unit_id == Unit.id)
        .join(ServiceInvoice, ServiceInvoice.id == UnitCharge.invoice_id)
        .join(ServiceCategory, ServiceCategory.id == ServiceInvoice.category_id)
        .join(Account, Account.id == Unit.owner_id)
        .where(Unit.building_id == building_id)
        .order_by(
            ServiceInvoice.billing_year.desc(),
            ServiceInvoice.billing_month.desc(),
            Unit.number,
            Unit.id,
        )
    )
    for unit, owner, year, month, amount, applied in db.execute(query):
        key = (unit.id, year, month)
        if key not in rows:
            rows[key] = CollectionRow(
                unit_id=unit.id,
                unit_number=unit.number,
                owner_name=owner,
                billing_year=year,
                billing_month=month,
                amount=Decimal("0.00"),
                applied=Decimal("0.00"),
                balance=Decimal("0.00"),
                overdue_balance=Decimal("0.00"),
                due_date=dates.get((year, month)),
            )
        row = rows[key]
        row.amount += Decimal(amount).scaleb(-2)
        row.applied += Decimal(applied).scaleb(-2)
        balance = Decimal(amount - applied).scaleb(-2)
        row.balance += balance
        if deadlines.is_overdue(balance, row.due_date, as_of):
            row.overdue_balance += balance
    return CollectionOverview(
        building_name=building.name,
        as_of=as_of,
        balance=sum((row.balance for row in rows.values()), Decimal("0.00")),
        overdue_balance=sum(
            (row.overdue_balance for row in rows.values()), Decimal("0.00")
        ),
        rows=list(rows.values()),
        deadlines=history,
    )
