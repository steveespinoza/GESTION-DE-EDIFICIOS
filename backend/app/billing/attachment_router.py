from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse

from app.billing import attachments
from app.billing.attachment_models import MAX_FILE_BYTES, FileKind
from app.billing.errors import InvoiceConflict, InvoiceNotFound
from app.dependencies import RequestSession
from app.identity.models import RoleName
from app.identity.router import require_role, require_session_header
from app.storage.files import FileStorage, StorageUnavailable
from app.storage.s3 import storage_factory

router = APIRouter(
    prefix="/api/admin/buildings/{building_id}/invoices/{invoice_id}/attachments",
    tags=["Archivos de factura"],
    dependencies=[Depends(require_role(RoleName.SUPERADMIN))],
)
StorageFactory = Annotated[Callable[[], FileStorage], Depends(storage_factory)]


def attachment_too_large() -> HTTPException:
    return HTTPException(
        status_code=413, detail="El archivo supera el límite de 10 MiB."
    )


async def read_body(request: Request) -> bytes:
    length = request.headers.get("content-length")
    if length is not None and length.isascii() and length.isdecimal():
        digits = length.lstrip("0") or "0"
        if len(digits) > 8 or int(digits) > MAX_FILE_BYTES:
            raise attachment_too_large()

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_FILE_BYTES:
            raise attachment_too_large()
        body.extend(chunk)
    if not body:
        raise HTTPException(status_code=422, detail="El archivo está vacío.")
    return bytes(body)


@router.get("")
def list_files(
    building_id: UUID, invoice_id: UUID, db: RequestSession
) -> list[attachments.AttachmentDetail]:
    try:
        return attachments.list_attachments(db, building_id, invoice_id)
    except InvoiceNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_session_header)],
)
async def upload_file(
    building_id: UUID,
    invoice_id: UUID,
    request: Request,
    response: Response,
    db: RequestSession,
    storage: StorageFactory,
    kind: FileKind,
    filename: Annotated[str, Query(min_length=1, max_length=200)],
) -> attachments.AttachmentDetail:
    try:
        await run_in_threadpool(
            attachments.require_invoice, db, building_id, invoice_id
        )
        body = await read_body(request)
        detail, created = await run_in_threadpool(
            attachments.attach_file,
            db,
            building_id,
            invoice_id,
            kind,
            filename,
            body,
            storage,
        )
    except InvoiceNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except InvoiceConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    except attachments.InvalidAttachment as error:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(error)
        ) from error
    except StorageUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return detail


@router.get(
    "/{attachment_id}/download",
    response_class=RedirectResponse,
    status_code=status.HTTP_303_SEE_OTHER,
)
def download_file(
    building_id: UUID,
    invoice_id: UUID,
    attachment_id: UUID,
    db: RequestSession,
    storage: StorageFactory,
) -> RedirectResponse:
    try:
        url = attachments.attachment_download(
            db, building_id, invoice_id, attachment_id, storage
        )
    except InvoiceNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except StorageUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
    return RedirectResponse(
        url,
        status_code=status.HTTP_303_SEE_OTHER,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )
