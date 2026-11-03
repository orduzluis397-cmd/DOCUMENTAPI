"""Tareas Celery.

`process_document` es por ahora un STUB: solo marca el documento como `processing`. El enrutador
de extracción (F0-09, `app/extraction/router.py`) se conectará aquí cuando existan los esquemas.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Document
from app.db.session import tenant_session
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def mark_processing(
    document_id: uuid.UUID,
    organization_id: uuid.UUID,
    factory: sessionmaker[Session] | None = None,
) -> str | None:
    """Pasa el documento de `queued` a `processing`. Devuelve el estado final o None."""
    with tenant_session(organization_id, factory) as session:
        doc = session.scalar(select(Document).where(Document.id == document_id).with_for_update())
        if doc is None:
            logger.warning("Documento %s no encontrado en la organización", document_id)
            return None
        if doc.status == "queued":
            doc.status = "processing"
        status = doc.status
        session.commit()
    # PENDIENTE F0-09: llamar al enrutador de extracción y guardar extractions/extracted_fields.
    logger.info("Documento %s en %s (extractor pendiente, F0-09)", document_id, status)
    return status


@celery_app.task(name="documents.process")
def process_document(document_id: str, organization_id: str) -> str | None:
    return mark_processing(uuid.UUID(document_id), uuid.UUID(organization_id))
