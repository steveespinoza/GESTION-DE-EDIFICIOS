from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.billing.invoice_schemas import AccountingPeriod
from app.collections.schemas import StatementCharge
from app.properties.owner_schemas import PaymentInstructions


class ReceiptInput(AccountingPeriod):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    revision: int = Field(strict=True, ge=0)
    reason: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]


class ReceiptCharge(StatementCharge):
    previous_reading: Decimal | None
    current_reading: Decimal | None
    original_common_amount: Decimal | None


class ReceiptPayment(BaseModel):
    id: UUID
    received_on: date
    amount: Decimal
    applied: Decimal
    reference: str | None


class ReceiptSnapshot(AccountingPeriod):
    schema_version: int = 1
    receipt_id: UUID
    version: int
    issued_at: datetime
    issued_by: str
    reason: str
    building_name: str
    address: str | None
    unit_number: str
    owner_name: str
    area_sqm: Decimal
    due_date: date | None
    charges: list[ReceiptCharge]
    previous_charges: list[ReceiptCharge]
    payments: list[ReceiptPayment]
    current_amount: Decimal
    current_applied: Decimal
    current_balance: Decimal
    previous_balance: Decimal
    total_pending: Decimal
    overdue_balance: Decimal
    credit: Decimal
    payment_instructions: PaymentInstructions


class ReceiptDetail(AccountingPeriod):
    id: UUID
    version: int
    issued_at: datetime
    issued_by: str
    reason: str
    due_date: date | None
    total_pending: Decimal
    credit: Decimal
    size_bytes: int
    sha256: str
