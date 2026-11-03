"""Almacenamiento de objetos (MinIO en local, R2/S3 en la nube) detrás de un protocolo mínimo."""

from functools import lru_cache
from typing import TYPE_CHECKING, Protocol

import boto3
from botocore.config import Config

from app.config import get_settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class ObjectStorage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...


class S3Storage:
    """Cliente S3 compatible (MinIO, R2, S3) sobre un bucket privado."""

    def __init__(self, client: "S3Client", bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()


@lru_cache
def get_storage() -> ObjectStorage:
    s = get_settings()
    client: S3Client = boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint_url or None,
        region_name=s.s3_region,
        aws_access_key_id=s.s3_access_key_id,
        aws_secret_access_key=s.s3_secret_access_key,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    return S3Storage(client, s.s3_bucket)
