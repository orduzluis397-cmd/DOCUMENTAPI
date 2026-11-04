"""Tarea Celery `documents.process` de punta a punta contra Postgres (`contable_ia_test`).

Carga por la API → tarea Celery (modo eager) → enrutador → `extractions`/`extracted_fields`,
estado final y auditoría, todo con el rol de la app bajo RLS. LLM y OCR son falsos (sin red).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.models import AuditEvent, Document, ExtractedField, Extraction, LlmCall
from app.extraction.ocr import OcrEngine, OcrUnavailableError
from app.llm.base import LLMClient
from app.workers import tasks
from app.workers.tasks import WorkerDeps, process, process_document
from tests.conftest import ApiHarness, Tenant
from tests.docs_fixtures import (
    CUENTA_COBRO_LINES,
    HOY,
    attached_document,
    cuenta_cobro_json,
    invoice_xml,
    invoice_zip,
    png_with_text,
    text_pdf,
)
from tests.fakes import (
    FAKE_MODEL,
    FAKE_PRICES,
    OUTPUT_TOKENS,
    FakeOcr,
    ScriptedTransport,
    scripted_llm,
)


def _settings(cap: str | None = "0.05", daily: str | None = "1000") -> Settings:
    return Settings(
        llm_provider="openai",
        llm_model_extraction=FAKE_MODEL,
        llm_max_cost_per_doc_usd=Decimal(cap) if cap else None,
        llm_daily_budget_usd=Decimal(daily) if daily else None,
        llm_monthly_budget_usd=Decimal("1000"),
        llm_max_output_tokens=OUTPUT_TOKENS,
        llm_max_retries=1,
    )


def _no_ocr(_s: Settings) -> OcrEngine:
    raise OcrUnavailableError("OCR no disponible: Tesseract no está instalado (prueba)")


@pytest.fixture
def worker(
    api: ApiHarness, app_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> WorkerDeps:
    """Dependencias del worker: el mismo almacenamiento falso de la API y la BD de pruebas."""
    deps = WorkerDeps(
        settings=_settings(),
        storage=api.storage,
        factory=app_factory,
        llm_client=lambda _s: pytest.fail("este documento no debería llamar al LLM"),
        ocr=_no_ocr,
        prices=lambda _s: FAKE_PRICES,
        hoy=HOY,
    )
    monkeypatch.setattr(tasks, "get_worker_deps", lambda: deps)
    return deps


def _upload(api: ApiHarness, tenant: Tenant, name: str, data: bytes) -> uuid.UUID:
    r = api.client.post("/documents", files=[("files", (name, data))], headers=tenant.headers)
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()[0]["id"])


def _run_task(doc_id: uuid.UUID, tenant: Tenant) -> str | None:
    result = process_document.apply(args=(str(doc_id), str(tenant.org_id)))
    value: str | None = result.get()
    return value


def test_zip_invoice_end_to_end(
    api: ApiHarness, worker: WorkerDeps, owner_engine: Engine, tenant_a: Tenant
) -> None:
    doc_id = _upload(api, tenant_a, "factura.zip", invoice_zip(attached_document(invoice_xml())))
    assert _run_task(doc_id, tenant_a) == "extracted"

    body = api.client.get(f"/documents/{doc_id}", headers=tenant_a.headers).json()
    assert body["status"] == "extracted"
    assert body["extraction"]["method"] == "xml_parser"
    fields = {f["name"]: f for f in body["fields"]}
    assert fields["numero"]["value"] == "SETP990000001"
    assert fields["total"]["value"] == "140600.00"
    assert fields["retenciones"]["value"] == "5850.00"
    # Tarifas y cantidades sin ceros de relleno, igual que GUIA.md y la ruta del LLM.
    assert fields["lineas[0].tarifa_iva"]["value"] == "19"
    assert fields["lineas[0].cantidad"]["value"] == "2"
    assert not any(f["is_doubtful"] for f in body["fields"])

    with Session(owner_engine) as s:
        doc = s.get_one(Document, doc_id)
        assert (doc.doc_type, doc.error) == ("factura", None)
        ext = s.scalars(select(Extraction).where(Extraction.document_id == doc_id)).one()
        assert ext.organization_id == tenant_a.org_id
        assert ext.trace_id
        assert ext.schema_version == "guia-0.1"
        # Regla dura 7: la ruta XML no llama al LLM.
        assert s.scalars(select(LlmCall).where(LlmCall.document_id == doc_id)).all() == []
        events = s.scalars(
            select(AuditEvent).where(AuditEvent.entity_id == str(doc_id)).order_by(AuditEvent.id)
        ).all()
        assert [e.action for e in events] == ["document.uploaded", "document.extracted"]
        assert events[-1].actor == "system:worker"
        assert events[-1].trace_id == ext.trace_id


def test_xml_with_bad_dv_needs_review(
    api: ApiHarness, worker: WorkerDeps, owner_engine: Engine, tenant_a: Tenant
) -> None:
    doc_id = _upload(api, tenant_a, "f.xml", invoice_xml(dv_emisor=0).encode("utf-8"))
    assert _run_task(doc_id, tenant_a) == "needs_review"
    with Session(owner_engine) as s:
        doubtful = s.scalars(
            select(ExtractedField.name)
            .join(Extraction, Extraction.id == ExtractedField.extraction_id)
            .where(Extraction.document_id == doc_id, ExtractedField.is_doubtful)
        ).all()
    assert set(doubtful) == {"nit_emisor", "dv_emisor"}


def test_pdf_with_llm_end_to_end(
    api: ApiHarness, worker: WorkerDeps, owner_engine: Engine, tenant_a: Tenant
) -> None:
    transport = ScriptedTransport(
        {
            "Clasificacion": [{"tipo_documento": "cuenta_cobro"}],
            # Siempre con el NIT del cobrador inválido: acaba dudoso tras el reintento.
            "CuentaCobro": [cuenta_cobro_json(nit_cobrador="CC-ABC")],
        }
    )
    clients: list[LLMClient] = []

    def build(_s: Settings) -> LLMClient:
        clients.append(scripted_llm(transport))
        return clients[-1]

    worker.llm_client = build
    doc_id = _upload(api, tenant_a, "cuenta.pdf", text_pdf(CUENTA_COBRO_LINES))
    assert _run_task(doc_id, tenant_a) == "needs_review"

    body = api.client.get(f"/documents/{doc_id}", headers=tenant_a.headers).json()
    assert body["extraction"]["method"] == "pdf_text"
    assert body["extraction"]["model"] == FAKE_MODEL
    assert body["extraction"]["prompt_version"] == "extraccion-2"
    fields = {f["name"]: f for f in body["fields"]}
    assert fields["nit_cobrador"]["is_doubtful"] is True
    assert fields["nit_cobrador"]["value"] is None
    assert fields["valor"]["is_doubtful"] is False
    assert fields["valor"]["value"] == "1500000.00"

    with Session(owner_engine) as s:
        ext = s.scalars(select(Extraction).where(Extraction.document_id == doc_id)).one()
        calls = s.scalars(select(LlmCall).where(LlmCall.document_id == doc_id)).all()
        assert len(calls) == 3  # clasificar + extraer + 1 reintento
        assert {c.trace_id for c in calls} == {ext.trace_id}
        assert sum((c.cost_usd for c in calls), Decimal(0)) == Decimal("0.006")
        doc = s.get_one(Document, doc_id)
        assert doc.doc_type == "cuenta_cobro"
        assert "nit_cobrador" in (doc.error or "")


def test_llm_without_cost_cap_fails_closed(
    api: ApiHarness, worker: WorkerDeps, owner_engine: Engine, tenant_a: Tenant
) -> None:
    worker.settings = _settings(cap=None)
    doc_id = _upload(api, tenant_a, "cuenta.pdf", text_pdf(CUENTA_COBRO_LINES))
    assert _run_task(doc_id, tenant_a) == "failed"
    with Session(owner_engine) as s:
        doc = s.get_one(Document, doc_id)
        assert "LLM_MAX_COST_PER_DOC_USD" in (doc.error or "")
        assert s.scalars(select(LlmCall).where(LlmCall.document_id == doc_id)).all() == []


def test_image_without_tesseract_fails_clearly(
    api: ApiHarness, worker: WorkerDeps, owner_engine: Engine, tenant_a: Tenant
) -> None:
    doc_id = _upload(api, tenant_a, "escaneo.png", png_with_text())
    assert _run_task(doc_id, tenant_a) == "failed"
    body = api.client.get(f"/documents/{doc_id}", headers=tenant_a.headers).json()
    assert body["extraction"]["method"] == "ocr"
    with Session(owner_engine) as s:
        assert "OCR no disponible" in (s.get_one(Document, doc_id).error or "")


def test_image_with_ocr_goes_to_llm(
    api: ApiHarness, worker: WorkerDeps, owner_engine: Engine, tenant_a: Tenant
) -> None:
    transport = ScriptedTransport(
        {
            "Clasificacion": [{"tipo_documento": "cuenta_cobro"}],
            "CuentaCobro": [cuenta_cobro_json()],
        }
    )
    worker.llm_client = lambda _s: scripted_llm(transport)
    worker.ocr = lambda _s: FakeOcr("\n".join(CUENTA_COBRO_LINES))
    doc_id = _upload(api, tenant_a, "escaneo.png", png_with_text())
    assert _run_task(doc_id, tenant_a) == "extracted"
    body = api.client.get(f"/documents/{doc_id}", headers=tenant_a.headers).json()
    assert body["extraction"]["method"] == "ocr"


def test_worker_respects_rls_and_is_idempotent(
    api: ApiHarness, worker: WorkerDeps, tenant_a: Tenant, tenant_b: Tenant
) -> None:
    doc_id = _upload(api, tenant_a, "f.xml", invoice_xml().encode("utf-8"))
    # Con la organización equivocada el worker no ve el documento.
    assert process(doc_id, tenant_b.org_id, worker) is None
    assert process(doc_id, tenant_a.org_id, worker) == "extracted"
    # Ya extraído: no se reprocesa ni se duplica la extracción.
    assert process(doc_id, tenant_a.org_id, worker) == "extracted"
    body = api.client.get(f"/documents/{doc_id}", headers=tenant_b.headers)
    assert body.status_code == 404


def _set_processing(owner_engine: Engine, doc_id: uuid.UUID, minutes_ago: int) -> None:
    with Session(owner_engine) as s:
        doc = s.get_one(Document, doc_id)
        doc.status = "processing"
        doc.processing_started_at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
        s.commit()


def test_processing_with_live_lease_is_not_taken(
    api: ApiHarness, worker: WorkerDeps, owner_engine: Engine, tenant_a: Tenant
) -> None:
    # Otro worker lo está procesando (lease vigente): una reentrega no lo toca.
    doc_id = _upload(api, tenant_a, "f.xml", invoice_xml().encode("utf-8"))
    _set_processing(owner_engine, doc_id, minutes_ago=1)
    assert _run_task(doc_id, tenant_a) == "processing"
    with Session(owner_engine) as s:
        assert s.scalars(select(Extraction).where(Extraction.document_id == doc_id)).all() == []


def test_processing_with_expired_lease_is_reclaimed(
    api: ApiHarness, worker: WorkerDeps, owner_engine: Engine, tenant_a: Tenant
) -> None:
    # El worker anterior se cayó hace más que el lease (900 s): Celery reentrega y se retoma.
    doc_id = _upload(api, tenant_a, "f.xml", invoice_xml().encode("utf-8"))
    _set_processing(owner_engine, doc_id, minutes_ago=30)
    assert _run_task(doc_id, tenant_a) == "extracted"
    with Session(owner_engine) as s:
        assert s.get_one(Document, doc_id).processing_started_at is None


def test_llm_without_daily_budget_fails_closed(
    api: ApiHarness, worker: WorkerDeps, owner_engine: Engine, tenant_a: Tenant
) -> None:
    worker.settings = _settings(daily=None)
    worker.llm_client = lambda _s: pytest.fail("sin presupuesto no se construye el cliente")
    doc_id = _upload(api, tenant_a, "cuenta.pdf", text_pdf(CUENTA_COBRO_LINES))
    assert _run_task(doc_id, tenant_a) == "failed"
    with Session(owner_engine) as s:
        assert "LLM_DAILY_BUDGET_USD" in (s.get_one(Document, doc_id).error or "")


def test_unexpected_error_marks_failed(
    api: ApiHarness, worker: WorkerDeps, owner_engine: Engine, tenant_a: Tenant
) -> None:
    doc_id = _upload(api, tenant_a, "f.xml", invoice_xml().encode("utf-8"))

    class BrokenStorage:
        def put(self, key: str, data: bytes, content_type: str) -> None: ...

        def get(self, key: str) -> bytes:
            raise ConnectionError("almacenamiento caído")

    worker.storage = BrokenStorage()
    assert _run_task(doc_id, tenant_a) == "failed"
    with Session(owner_engine) as s:
        doc = s.get_one(Document, doc_id)
        assert "almacenamiento caído" in (doc.error or "")
        actions = s.scalars(
            select(AuditEvent.action).where(AuditEvent.entity_id == str(doc_id))
        ).all()
        assert "document.failed" in actions
