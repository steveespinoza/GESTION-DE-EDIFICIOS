from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.billing.invoice_schemas import AccountingPeriod
from app.documents.schemas import ReceiptDetail


class BatchInput(AccountingPeriod):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    due_date: date
    deadline_revision: int = Field(strict=True, ge=0)
    reason: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]


class BatchItemDetail(BaseModel):
    unit_id: UUID
    unit_number: str
    revision: int
    status: Literal["PENDING", "ISSUED", "FAILED", "SKIPPED"]
    attempts: int
    last_attempt_at: datetime | None
    last_attempt_by: str | None
    error_code: str | None
    error_message: str | None
    retryable: bool
    receipt: ReceiptDetail | None


class BatchSummary(AccountingPeriod):
    id: UUID
    due_date: date
    deadline_revision: int
    reason: str
    created_at: datetime
    created_by: str
    pending: int
    issued: int
    failed: int
    skipped: int


class BatchDetail(BatchSummary):
    items: list[BatchItemDetail]
