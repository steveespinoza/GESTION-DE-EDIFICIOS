from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class ChargeAdjustmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    revision: int = Field(strict=True, ge=0)
    new_amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    reason: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]


class ChargeAdjustmentDetail(BaseModel):
    id: UUID
    charge_id: UUID
    unit_number: str
    service: str
    billing_year: int
    billing_month: int
    revision: int
    previous_amount: Decimal
    new_amount: Decimal
    difference: Decimal
    released_credit: Decimal
    reason: str
    recorded_by: str
    recorded_at: datetime
