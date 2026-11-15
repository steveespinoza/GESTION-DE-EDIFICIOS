from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.billing import invoices
from app.billing.invoice_schemas import (
    InvoiceDetail,
    InvoiceSummary,
    LinearInvoiceInput,
)
from app.dependencies import RequestSession
from app.identity.models import RoleName
from app.identity.router import require_role, require_session_header

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


@router.get("/{invoice_id}")
def read_invoice(
    building_id: UUID, invoice_id: UUID, db: RequestSession
) -> InvoiceDetail:
    try:
        return invoices.find_invoice(db, building_id, invoice_id)
    except invoices.InvoiceNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_session_header)],
)
def create_invoice(
    building_id: UUID, data: LinearInvoiceInput, db: RequestSession
) -> InvoiceDetail:
    try:
        return invoices.create_linear_invoice(db, building_id, data)
    except invoices.InvoiceNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except invoices.InvoiceConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
