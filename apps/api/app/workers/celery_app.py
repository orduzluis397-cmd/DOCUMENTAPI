"""Aplicación Celery (broker y resultados en Redis)."""

from celery import Celery

from app.config import get_settings


def create_celery() -> Celery:
    s = get_settings()
    app = Celery(
        "contable_ia",
        broker=s.celery_broker_url,
        backend=s.celery_result_backend,
        include=["app.workers.tasks"],
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="America/Bogota",
        enable_utc=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_always_eager=s.celery_task_always_eager,
        task_eager_propagates=True,
    )
    return app


celery_app = create_celery()
