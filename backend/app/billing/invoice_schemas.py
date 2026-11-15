from datetime import date
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InvoicePeriod(BaseModel):
    billing_year: int = Field(strict=True, ge=2020, le=9999)
    billing_month: int = Field(strict=True, ge=1, le=12)
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


class InvoiceSummary(InvoicePeriod):
    id: UUID
    category_id: UUID
    category_name: str
    total_amount: Decimal


class ChargeDetail(BaseModel):
    unit_id: UUID
    unit_number: str
    amount: Decimal


class InvoiceDetail(InvoiceSummary):
    charges: list[ChargeDetail]
