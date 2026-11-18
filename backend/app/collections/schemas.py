from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.billing.adjustment_schemas import ChargeAdjustmentDetail
from app.billing.invoice_schemas import AccountingPeriod


class PaymentValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    received_on: date
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    reference: Annotated[str, StringConstraints(max_length=120)] | None = None

    @field_validator("reference", mode="before")
    @classmethod
    def normalize_reference(cls, value: object) -> object:
        return (value.strip() or None) if isinstance(value, str) else value


class PaymentInput(AccountingPeriod, PaymentValues):
    request_id: UUID


class StatementCharge(AccountingPeriod):
    id: UUID
    service: str
    coverage_end: date
    amount: Decimal
    original_amount: Decimal
    adjustment: Decimal
    applied: Decimal
    balance: Decimal
    consumption: Decimal | None


class AppliedCharge(AccountingPeriod):
    id: UUID
    charge_id: UUID
    service: str
    amount: Decimal
    released: Decimal
    net_amount: Decimal
    applied_at: datetime
    applied_by: str | None
    automatic: bool


class CarryForwardDetail(AccountingPeriod):
    charge_id: UUID
    source_year: int
    source_month: int
    service: str
    amount: Decimal
    balance: Decimal
    recorded_at: datetime
    recorded_by: str | None


class PaymentDetail(AccountingPeriod):
    id: UUID
    received_on: date
    amount: Decimal
    credit: Decimal
    reference: str | None
    applications: list[AppliedCharge] = Field(default_factory=list)


class Statement(BaseModel):
    unit_number: str
    building_name: str
    balance: Decimal
    credit: Decimal
    charges: list[StatementCharge]
    payments: list[PaymentDetail]
    carry_forwards: list[CarryForwardDetail]
    adjustments: list[ChargeAdjustmentDetail]
