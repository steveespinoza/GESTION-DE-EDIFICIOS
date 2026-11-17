from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.storage.files import MAX_FILE_BYTES, FileStorage
from app.storage.s3 import storage_factory

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


def private_download(url: str) -> RedirectResponse:
    return RedirectResponse(
        url,
        status_code=303,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )
