from typing import Protocol


class StorageUnavailable(Exception):
    pass


class FileStorage(Protocol):
    def put(self, key: str, body: bytes, content_type: str) -> None: ...
    def download_url(self, key: str, filename: str) -> str: ...
