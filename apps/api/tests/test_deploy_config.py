"""Configuración de despliegue de la demo: Celery con TLS (Upstash) y S3 de Supabase."""

import ssl

from botocore.stub import Stubber

from app.config import Settings
from app.storage import S3Storage, build_s3_client
from app.workers.celery_app import celery_config

SUPABASE_S3 = "https://abcdefghijklmnop.storage.supabase.co/storage/v1/s3"
KEY = "org/x/documents/y.pdf"


def test_celery_tls_for_rediss() -> None:
    s = Settings(
        celery_broker_url="rediss://default:x@demo.upstash.io:6379",
        celery_result_backend="",
        celery_broker_polling_interval_s=30,
    )
    conf = celery_config(s)
    assert conf["broker_use_ssl"] == {"ssl_cert_reqs": ssl.CERT_REQUIRED}
    assert "redis_backend_use_ssl" not in conf
    assert conf["task_ignore_result"] is True
    assert conf["broker_transport_options"]["polling_interval"] == 30
    assert conf["broker_transport_options"]["visibility_timeout"] >= 2 * s.processing_lease_s


def test_celery_local_without_tls() -> None:
    conf = celery_config(Settings())
    assert "broker_use_ssl" not in conf
    assert "task_ignore_result" not in conf
    assert "broker_transport_options" not in conf


def test_supabase_s3_by_configuration_only() -> None:
    s = Settings(
        s3_endpoint_url=SUPABASE_S3,
        s3_region="sa-east-1",
        s3_bucket="contable-ia-documents",
        s3_access_key_id="clave-de-prueba",
        s3_secret_access_key="secreto-de-prueba",  # noqa: S106 - valor falso de prueba
    )
    client = build_s3_client(s)
    assert client.meta.endpoint_url == SUPABASE_S3
    assert client.meta.region_name == "sa-east-1"
    assert client.meta.config.s3 == {"addressing_style": "path"}  # type: ignore[attr-defined]

    storage = S3Storage(client, s.s3_bucket)
    with Stubber(client) as stub:
        stub.add_response(
            "put_object",
            {},
            {
                "Bucket": "contable-ia-documents",
                "Key": KEY,
                "Body": b"%PDF",
                "ContentType": "application/pdf",
            },
        )
        stub.add_response("delete_object", {}, {"Bucket": "contable-ia-documents", "Key": KEY})
        storage.put(KEY, b"%PDF", "application/pdf")
        storage.delete(KEY)
        stub.assert_no_pending_responses()
