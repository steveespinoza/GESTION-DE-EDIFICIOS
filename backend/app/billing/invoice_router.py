from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.billing import corrections, invoices
from app.billing.invoice_schemas import (
    AccountingPeriod,
    InvoiceDetail,
    InvoiceSummary,
    LinearInvoiceCorrection,
    LinearInvoiceInput,
    MeteredInvoiceCorrection,
    MeteredInvoiceInput,
    MeterReadingDefaults,
)
from app.dependencies import RequestSession
from app.identity.models import RoleName
from app.identity.router import CurrentUser, require_role, require_session_header

router = APIRouter(
    prefix="/api/admin/buildings/{building_id}/invoices",
    tags=["Facturas"],
    dependencies=[Depends(require_role(RoleName.SUPERADMIN))],
)


@router.get("")
def list_invoices(building_id: UUID, db: RequestSession) -> list[InvoiceSummary]:
    try:
        return invoices.list_invoices(db, building_id)
    except invoices.InvoiceNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error


@router.get("/meter-readings")
def meter_readings(
    building_id: UUID,
    category_id: UUID,
    db: RequestSession,
    billing_year: Annotated[int, Query(ge=2020, le=9999)],
    billing_month: Annotated[int, Query(ge=1, le=12)],
) -> list[MeterReadingDefaults]:
    try:
        period = AccountingPeriod(
            billing_year=billing_year, billing_month=billing_month
        )
        return invoices.reading_defaults(db, building_id, category_id, period)
    except invoices.InvoiceNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except invoices.InvoiceConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error


@router.get("/{invoice_id}", response_model_exclude_none=True)
def read_invoice(
    building_id: UUID, invoice_id: UUID, db: RequestSession
) -> InvoiceDetail:
    try:
        return invoices.find_invoice(db, building_id, invoice_id)
    except invoices.InvoiceNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error


@router.put(
    "/{invoice_id}",
    dependencies=[Depends(require_session_header)],
    response_model_exclude_none=True,
)
def correct_invoice(
    building_id: UUID,
    invoice_id: UUID,
    data: LinearInvoiceCorrection | MeteredInvoiceCorrection,
    db: RequestSession,
    user: CurrentUser,
) -> InvoiceDetail:
    try:
        return corrections.correct_invoice(db, building_id, invoice_id, data, user.id)
    except invoices.InvoiceNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except invoices.InvoiceConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_session_header)],
    response_model_exclude_none=True,
)
def create_invoice(
    building_id: UUID,
    data: LinearInvoiceInput | MeteredInvoiceInput,
    db: RequestSession,
) -> InvoiceDetail:
    try:
        return invoices.create_invoice(db, building_id, data)
    except invoices.InvoiceNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except invoices.InvoiceConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
