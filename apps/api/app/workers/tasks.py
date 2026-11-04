"""Tareas Celery: `documents.process` corre el enrutador de extracción (F0-09/F0-10).

Pasos, todos bajo RLS con la organización del documento:

1. Transacción corta: `queued` → `processing` (con bloqueo de fila; idempotente).
2. Lee el archivo del almacenamiento y corre el enrutador. Las llamadas LLM escriben `llm_calls`
   en sus propias transacciones (quedan aunque luego algo falle).
3. Transacción final: `extractions` + `extracted_fields`, estado `extracted` / `needs_review` /
   `failed` y el evento de auditoría, en el mismo commit (regla dura 5).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db.models import Document, ExtractedField, Extraction
from app.db.session import tenant_session
from app.extraction.ocr import OcrEngine, TesseractOcr
from app.extraction.router import RouterConfig, extract_document
from app.extraction.types import ExtractionOutcome
from app.governance import audit
from app.llm.base import LLMClient, LLMNotConfiguredError
from app.llm.factory import build_llm_client
from app.llm.pricing import PriceTable
from app.observability.llm_calls import TrackedLLM
from app.storage import ObjectStorage, get_storage
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

ACTOR = "system:worker"
_PROCESSABLE = ("queued", "processing")


@dataclass
class WorkerDeps:
    """Dependencias del procesamiento; las pruebas inyectan almacenamiento, LLM y OCR falsos."""

    settings: Settings
    storage: ObjectStorage
    factory: sessionmaker[Session] | None = None
    llm_client: Callable[[Settings], LLMClient] = build_llm_client
    ocr: Callable[[Settings], OcrEngine] = field(
        default=lambda s: TesseractOcr(s.tesseract_cmd, s.ocr_lang, s.tessdata_prefix)
    )
    prices: Callable[[Settings], PriceTable] = field(
        default=lambda s: PriceTable.load(s.llm_prices_path)
    )
    hoy: date | None = None


def get_worker_deps() -> WorkerDeps:
    return WorkerDeps(settings=get_settings(), storage=get_storage())


def mark_processing(
    document_id: uuid.UUID,
    organization_id: uuid.UUID,
    factory: sessionmaker[Session] | None = None,
) -> tuple[str, str] | None:
    """`queued` → `processing`. Devuelve `(estado, storage_key)` o None si no existe en la org."""
    with tenant_session(organization_id, factory) as session:
        doc = session.scalar(select(Document).where(Document.id == document_id).with_for_update())
        if doc is None:
            logger.warning("Documento %s no encontrado en la organización", document_id)
            return None
        if doc.status == "queued":
            doc.status = "processing"
        result = (doc.status, doc.storage_key)
        session.commit()
    return result


def _llm_factory(
    deps: WorkerDeps, organization_id: uuid.UUID, document_id: uuid.UUID, trace_id: str
) -> Callable[[], TrackedLLM]:
    def build() -> TrackedLLM:
        s = deps.settings
        cap = s.llm_max_cost_per_doc_usd
        if cap is None:
            raise LLMNotConfiguredError(
                "Falta LLM_MAX_COST_PER_DOC_USD: sin tope por documento no se llama al LLM."
            )
        return TrackedLLM(
            deps.llm_client(s),
            deps.prices(s),
            organization_id=organization_id,
            document_id=document_id,
            trace_id=trace_id,
            max_cost_usd=Decimal(cap),
            factory=deps.factory,
        )

    return build


def save_outcome(
    document_id: uuid.UUID,
    organization_id: uuid.UUID,
    outcome: ExtractionOutcome,
    trace_id: str,
    factory: sessionmaker[Session] | None = None,
) -> str:
    """Guarda extracción, campos, estado y auditoría en una sola transacción."""
    with tenant_session(organization_id, factory) as session:
        doc = session.scalar(select(Document).where(Document.id == document_id).with_for_update())
        if doc is None:
            raise LookupError(f"Documento {document_id} no encontrado en la organización")
        extraction = Extraction(
            id=uuid.uuid4(),
            organization_id=organization_id,
            document_id=document_id,
            doc_type=outcome.doc_type,
            method=outcome.method,
            model=outcome.model,
            prompt_version=outcome.prompt_version,
            schema_version=outcome.schema_version,
            trace_id=trace_id,
            raw_output=outcome.raw_output or None,
        )
        session.add(extraction)
        session.flush()
        session.add_all(
            ExtractedField(
                organization_id=organization_id,
                extraction_id=extraction.id,
                name=f.name,
                value=f.value,
                is_doubtful=f.is_doubtful,
            )
            for f in outcome.fields
        )
        old_status = doc.status
        doc.status = outcome.status
        doc.doc_type = outcome.doc_type
        doc.error = outcome.error
        audit.record(
            session,
            organization_id=organization_id,
            actor=ACTOR,
            action=f"document.{outcome.status}",
            entity="documents",
            entity_id=document_id,
            old_value={"status": old_status},
            new_value={
                "status": outcome.status,
                "doc_type": outcome.doc_type,
                "method": outcome.method,
                "extraction_id": str(extraction.id),
                "doubtful_fields": outcome.doubtful_fields,
                "error": outcome.error,
            },
            model=outcome.model,
            prompt_version=outcome.prompt_version,
            trace_id=trace_id,
        )
        session.commit()
    return outcome.status


def _mark_failed(
    document_id: uuid.UUID,
    organization_id: uuid.UUID,
    error: str,
    trace_id: str,
    factory: sessionmaker[Session] | None,
) -> str:
    with tenant_session(organization_id, factory) as session:
        doc = session.scalar(select(Document).where(Document.id == document_id).with_for_update())
        if doc is None:
            return "failed"
        old = doc.status
        doc.status = "failed"
        doc.error = error[:4000]
        audit.record(
            session,
            organization_id=organization_id,
            actor=ACTOR,
            action="document.failed",
            entity="documents",
            entity_id=document_id,
            old_value={"status": old},
            new_value={"status": "failed", "error": doc.error},
            trace_id=trace_id,
        )
        session.commit()
    return "failed"


def process(document_id: uuid.UUID, organization_id: uuid.UUID, deps: WorkerDeps) -> str | None:
    """Procesa un documento de punta a punta. Devuelve el estado final o None si no existe."""
    marked = mark_processing(document_id, organization_id, deps.factory)
    if marked is None:
        return None
    status, storage_key = marked
    if status != "processing":
        logger.info("Documento %s ya en %s; no se reprocesa", document_id, status)
        return status

    trace_id = uuid.uuid4().hex
    s = deps.settings
    config = RouterConfig(
        model_extraction=s.llm_model_extraction,
        model_classification=s.llm_model_classification,
        max_retries=s.llm_max_retries,
        max_input_chars=s.llm_max_input_chars,
        pdf_min_chars_per_page=s.pdf_min_chars_per_page,
        ocr_dpi=s.ocr_dpi,
        ocr_max_pages=s.ocr_max_pages,
    )
    try:
        data = deps.storage.get(storage_key)
        outcome = extract_document(
            data,
            config=config,
            llm_factory=_llm_factory(deps, organization_id, document_id, trace_id),
            ocr_factory=lambda: deps.ocr(s),
            trace_id=trace_id,
            hoy=deps.hoy,
        )
        return save_outcome(document_id, organization_id, outcome, trace_id, deps.factory)
    except Exception as exc:
        logger.exception("Fallo inesperado procesando %s (trace %s)", document_id, trace_id)
        return _mark_failed(
            document_id,
            organization_id,
            f"Error inesperado: {type(exc).__name__}: {exc}",
            trace_id,
            deps.factory,
        )


@celery_app.task(name="documents.process")
def process_document(document_id: str, organization_id: str) -> str | None:
    return process(uuid.UUID(document_id), uuid.UUID(organization_id), get_worker_deps())
