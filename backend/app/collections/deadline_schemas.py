from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.billing.invoice_schemas import AccountingPeriod


class DeadlineInput(AccountingPeriod):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    revision: int = Field(strict=True, ge=0)
    due_date: date
    reason: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]


class DeadlineDetail(AccountingPeriod):
    id: UUID
    revision: int
    due_date: date
    reason: str
    recorded_by: str
    recorded_at: datetime


class CollectionRow(AccountingPeriod):
    unit_id: UUID
    unit_number: str
    owner_name: str
    amount: Decimal
    applied: Decimal
    balance: Decimal
    overdue_balance: Decimal
    due_date: date | None


class CollectionOverview(BaseModel):
    building_name: str
    as_of: date
    balance: Decimal
    overdue_balance: Decimal
    rows: list[CollectionRow]
    deadlines: list[DeadlineDetail]
