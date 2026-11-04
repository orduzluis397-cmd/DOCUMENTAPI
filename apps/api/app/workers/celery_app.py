"""Aplicación Celery (broker y resultados en Redis).

- `rediss://` (Upstash en la demo): TLS con verificación de certificado obligatoria.
- `CELERY_RESULT_BACKEND` vacío: sin backend de resultados (la API no los lee; ahorra comandos
  en la cuota de Upstash).
- `CELERY_BROKER_POLLING_INTERVAL_S`: segundos de cada BRPOP en vacío; la tarea llega igual al
  instante, solo baja el número de comandos mientras no hay trabajo.
"""

import ssl
from typing import Any

from celery import Celery

from app.config import Settings, get_settings

_TLS = {"ssl_cert_reqs": ssl.CERT_REQUIRED}


def _is_tls(url: str | None) -> bool:
    return bool(url) and str(url).startswith("rediss://")


def celery_config(s: Settings) -> dict[str, Any]:
    conf: dict[str, Any] = {
        "task_serializer": "json",
        "accept_content": ["json"],
        "result_serializer": "json",
        "timezone": "America/Bogota",
        "enable_utc": True,
        "task_acks_late": True,
        "worker_prefetch_multiplier": 1,
        "task_always_eager": s.celery_task_always_eager,
        "task_eager_propagates": True,
        "broker_connection_retry_on_startup": True,
        "worker_send_task_events": False,
    }
    backend = s.celery_result_backend.strip() or None
    if backend is None:
        conf["task_ignore_result"] = True
    if _is_tls(s.celery_broker_url):
        conf["broker_use_ssl"] = dict(_TLS)
    if _is_tls(backend):
        conf["redis_backend_use_ssl"] = dict(_TLS)
    if s.celery_broker_polling_interval_s is not None:
        conf["broker_transport_options"] = {
            "polling_interval": s.celery_broker_polling_interval_s,
            # Más que el lease de procesamiento: no reentregar una tarea que sigue viva.
            "visibility_timeout": max(3600, s.processing_lease_s * 2),
        }
    return conf


def create_celery() -> Celery:
    s = get_settings()
    app = Celery(
        "contable_ia",
        broker=s.celery_broker_url,
        backend=s.celery_result_backend.strip() or None,
        include=["app.workers.tasks"],
    )
    app.conf.update(celery_config(s))
    return app


celery_app = create_celery()
