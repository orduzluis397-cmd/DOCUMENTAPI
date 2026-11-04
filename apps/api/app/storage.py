"""Almacenamiento de objetos detrás de un protocolo mínimo.

MinIO en local; en la demo, Supabase Storage por su endpoint compatible con S3
(`https://<ref>.storage.supabase.co/storage/v1/s3`, región del proyecto, claves S3 del panel).
Todo cambia solo por configuración (`S3_*`). Direccionamiento por ruta (path-style), que piden
MinIO y Supabase. Checksums solo cuando la operación los exige: los S3 compatibles no siempre
aceptan los CRC que boto3 añade por defecto desde 1.36. El bucket debe ser privado.
"""

from functools import lru_cache
from typing import TYPE_CHECKING, Protocol

import boto3
from botocore.config import Config

from app.config import Settings, get_settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class ObjectStorage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class S3Storage:
    """Cliente S3 compatible (MinIO, R2, S3) sobre un bucket privado."""

    def __init__(self, client: "S3Client", bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        # Idempotente: borrar una clave que no existe no es error en S3.
        self._client.delete_object(Bucket=self._bucket, Key=key)


def build_s3_client(s: Settings) -> "S3Client":
    return boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint_url or None,
        region_name=s.s3_region,
        aws_access_key_id=s.s3_access_key_id,
        aws_secret_access_key=s.s3_secret_access_key,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
            connect_timeout=10,
            read_timeout=60,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


@lru_cache
def get_storage() -> ObjectStorage:
    s = get_settings()
    return S3Storage(build_s3_client(s), s.s3_bucket)
