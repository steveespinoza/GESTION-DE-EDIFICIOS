from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.billing.invoice_schemas import AccountingPeriod
from app.collections.report_models import ReportStatus
from app.collections.schemas import PaymentInput, PaymentValues


class ReportUpload(PaymentInput):
    filename: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]


class RejectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]
    proof_revision: int = Field(default=0, strict=True, ge=0)


class ApprovalInput(PaymentValues):
    proof_revision: int = Field(default=0, strict=True, ge=0)


class ProofUpload(RejectionInput):
    request_id: UUID
    filename: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]


class ProofDetail(BaseModel):
    revision: int
    filename: str
    size_bytes: int
    uploaded_by: str
    uploaded_at: datetime
    reason: str | None


class ReportDetail(AccountingPeriod):
    id: UUID
    unit_id: UUID
    unit_number: str
    status: ReportStatus
    received_on: date
    amount: Decimal
    reference: str | None
    filename: str
    submitted_at: datetime
    reviewed_at: datetime | None
    payment_id: UUID | None
    rejection_reason: str | None
    proof_revision: int
