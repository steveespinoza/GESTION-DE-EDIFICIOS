import os
from collections.abc import Callable
from functools import lru_cache
from urllib.parse import quote

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.storage.files import FileStorage, StorageUnavailable

DOWNLOAD_SECONDS = 300


class S3FileStorage:
    def __init__(self, client, bucket: str):
        self.client = client
        self.bucket = bucket

    def put(self, key: str, body: bytes, content_type: str) -> None:
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
                CacheControl="private, no-store",
            )
        except (BotoCoreError, ClientError) as error:
            raise StorageUnavailable(
                "No se pudo guardar el archivo en el almacenamiento."
            ) from error

    def download_url(self, key: str, filename: str) -> str:
        encoded = quote(filename, safe="")
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": key,
                    "ResponseContentDisposition": f"attachment; filename=\"archivo\"; filename*=UTF-8''{encoded}",
                    "ResponseContentType": "application/octet-stream",
                    "ResponseCacheControl": "private, no-store",
                },
                ExpiresIn=DOWNLOAD_SECONDS,
            )
        except (BotoCoreError, ClientError) as error:
            raise StorageUnavailable(
                "No se pudo generar la descarga del archivo."
            ) from error


@lru_cache(maxsize=1)
def configured_storage() -> FileStorage:
    bucket = os.environ.get("S3_BUCKET", "").strip()
    region = os.environ.get("AWS_REGION", "").strip()
    if not bucket or not region:
        raise StorageUnavailable("El almacenamiento de archivos no está configurado.")

    try:
        client = boto3.client(
            "s3",
            region_name=region,
            config=Config(
                signature_version="s3v4",
                connect_timeout=3,
                read_timeout=12,
                retries={"total_max_attempts": 2},
            ),
        )
    except (BotoCoreError, ClientError) as error:
        raise StorageUnavailable(
            "No se pudo iniciar el almacenamiento de archivos."
        ) from error
    return S3FileStorage(client, bucket)


def storage_factory() -> Callable[[], FileStorage]:
    return configured_storage
