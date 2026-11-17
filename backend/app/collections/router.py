from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from app.collections import service
from app.collections.schemas import PaymentDetail, PaymentInput, Statement
from app.dependencies import RequestSession
from app.identity.models import RoleName
from app.identity.router import require_role, require_session_header
from app.identity.schemas import SessionUser

router = APIRouter(tags=["Cobranzas"])
Admin = Annotated[SessionUser, Depends(require_role(RoleName.SUPERADMIN))]
Owner = Annotated[SessionUser, Depends(require_role(RoleName.OWNER))]
ADMIN_UNIT = "/api/admin/buildings/{building_id}/units/{unit_id}"


@router.get(f"{ADMIN_UNIT}/statement")
def admin_statement(
    building_id: UUID, unit_id: UUID, db: RequestSession, _user: Admin
) -> Statement:
    try:
        return service.read_statement(db, unit_id, building_id=building_id)
    except service.UnitNotFound as error:
        raise HTTPException(404, "Unidad no encontrada.") from error


@router.get("/api/owner/properties/{unit_id}/statement")
def owner_statement(unit_id: UUID, db: RequestSession, user: Owner) -> Statement:
    try:
        return service.read_statement(db, unit_id, owner_id=user.id)
    except service.UnitNotFound as error:
        raise HTTPException(404, "Unidad no encontrada.") from error


@router.post(
    f"{ADMIN_UNIT}/payments",
    status_code=201,
    dependencies=[Depends(require_session_header)],
)
def register_payment(
    building_id: UUID,
    unit_id: UUID,
    data: PaymentInput,
    db: RequestSession,
    user: Admin,
    response: Response,
) -> PaymentDetail:
    try:
        payment, created = service.record_payment(
            db, building_id, unit_id, user.id, data
        )
    except service.UnitNotFound as error:
        raise HTTPException(404, "Unidad no encontrada.") from error
    except service.PaymentConflict as error:
        raise HTTPException(409, str(error)) from error
    if not created:
        response.status_code = 200
    return payment
