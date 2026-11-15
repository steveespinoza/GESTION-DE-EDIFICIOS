from datetime import date
from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

METER_LIMIT_MILLI = 100_000_000
MeterValue = Annotated[Decimal, Field(ge=0, lt=100_000, decimal_places=3)]


class AccountingPeriod(BaseModel):
    billing_year: int = Field(strict=True, ge=2020, le=9999)
    billing_month: int = Field(strict=True, ge=1, le=12)


class InvoicePeriod(AccountingPeriod):
    start_date: date
    end_date: date


class LinearInvoiceInput(InvoicePeriod):
    model_config = ConfigDict(extra="forbid")

    category_id: UUID
    total_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)

    @model_validator(mode="after")
    def dates_in_order(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError(
                "La fecha de fin debe ser igual o posterior a la de inicio."
            )
        return self


class MeterReadingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_id: UUID
    previous_reading: MeterValue
    current_reading: MeterValue
    rollover_confirmed: bool = Field(default=False, strict=True)


class MeteredInvoiceInput(LinearInvoiceInput):
    total_volume: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    readings: list[MeterReadingInput] = Field(min_length=1)


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
    unit_id: UUID
    unit_number: str
    amount: Decimal
    meter: MeteredChargeDetail | None = None


class InvoiceDetail(InvoiceSummary):
    charges: list[ChargeDetail]
    total_volume: Decimal | None = None
    common_volume: Decimal | None = None
