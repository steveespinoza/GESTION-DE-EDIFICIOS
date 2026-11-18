from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.billing.adjustment_schemas import ChargeAdjustmentDetail

METER_LIMIT_MILLI = 100_000_000
MeterValue = Annotated[Decimal, Field(ge=0, lt=100_000, decimal_places=3)]


class AccountingPeriod(BaseModel):
    billing_year: int = Field(strict=True, ge=2020, le=9999)
    billing_month: int = Field(strict=True, ge=1, le=12)


class InvoiceDates(BaseModel):
    start_date: date
    end_date: date


class InvoicePeriod(InvoiceDates, AccountingPeriod):
    pass


class InvoiceValues(InvoiceDates):
    model_config = ConfigDict(extra="forbid")

    total_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)

    @model_validator(mode="after")
    def dates_in_order(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError(
                "La fecha de fin debe ser igual o posterior a la de inicio."
            )
        return self


class LinearInvoiceInput(InvoiceValues, AccountingPeriod):
    category_id: UUID


class MeterReadingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_id: UUID
    previous_reading: MeterValue
    current_reading: MeterValue
    rollover_confirmed: bool = Field(default=False, strict=True)


class MeteredValues(BaseModel):
    total_volume: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    readings: list[MeterReadingInput] = Field(min_length=1)


class MeteredInvoiceInput(LinearInvoiceInput, MeteredValues):
    pass


class LinearInvoiceCorrection(InvoiceValues):
    revision: int = Field(strict=True, ge=0)
    reason: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]


class MeteredInvoiceCorrection(LinearInvoiceCorrection, MeteredValues):
    pass


class MeterReadingDefaults(BaseModel):
    unit_id: UUID
    unit_number: str
    previous_reading: Decimal | None


class InvoiceSummary(InvoicePeriod):
    id: UUID
    category_id: UUID
    category_name: str
    total_amount: Decimal


class MeteredChargeDetail(BaseModel):
    previous_reading: Decimal
    current_reading: Decimal
    consumption: Decimal
    own_amount: Decimal
    common_amount: Decimal
    rolled_over: bool


class ChargeDetail(BaseModel):
    id: UUID
    unit_id: UUID
    unit_number: str
    amount: Decimal
    adjusted_amount: Decimal
    adjustment_revision: int = 0
    meter: MeteredChargeDetail | None = None


class CorrectionDetail(BaseModel):
    revision: int
    reason: str
    corrected_by: str
    corrected_at: datetime


class InvoiceDetail(InvoiceSummary):
    adjusted_total_amount: Decimal
    charges: list[ChargeDetail]
    total_volume: Decimal | None = None
    common_volume: Decimal | None = None
    revision: int
    accounting_locked: bool
    corrections: list[CorrectionDetail] = Field(default_factory=list)
    adjustments: list[ChargeAdjustmentDetail] = Field(default_factory=list)
