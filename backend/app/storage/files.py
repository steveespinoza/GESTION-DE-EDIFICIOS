from typing import Protocol


class StorageUnavailable(Exception):
    pass


class FileStorage(Protocol):
    def put(self, key: str, body: bytes, content_type: str) -> None: ...
    def download_url(self, key: str, filename: str) -> str: ...


MAX_FILE_BYTES = 10 * 1024 * 1024


class InvalidAttachment(Exception):
    pass


def validate_attachment(filename: str, body: bytes) -> str:
    if not filename or any(
        character in "/\\" or ord(character) < 32 or ord(character) == 127
        for character in filename
    ):
        raise InvalidAttachment("El nombre del archivo no es válido.")
    extension = filename.rpartition(".")[2].lower()
    if extension == "pdf" and body.startswith(b"%PDF-"):
        return "application/pdf"
    if extension == "png" and body.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if extension in {"jpg", "jpeg"} and body.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    raise InvalidAttachment("Selecciona un archivo PDF, PNG o JPEG válido.")
