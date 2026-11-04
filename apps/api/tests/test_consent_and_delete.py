"""Autorización de uso de datos antes de subir, y borrado de documentos (CR-005)."""

import uuid

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import (
    AuditEvent,
    DataUseConsent,
    Document,
    ExtractedField,
    Extraction,
    LlmCall,
)
from tests.conftest import ApiHarness, Tenant, create_tenant

PDF = b"%PDF-1.7\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest.fixture
def tenant_sin_consent(owner_engine: Engine, migrated: None) -> Tenant:
    return create_tenant(owner_engine, "org-sin-consent", consent=False)


def _upload(api: ApiHarness, tenant: Tenant) -> int:
    r = api.client.post(
        "/documents",
        files=[("files", ("f.pdf", PDF, "application/pdf"))],
        headers=tenant.headers,
    )
    return r.status_code


def test_consent_is_draft_and_not_accepted(api: ApiHarness, tenant_sin_consent: Tenant) -> None:
    r = api.client.get("/consent", headers=tenant_sin_consent.headers)
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] is False
    assert body["accepted_at"] is None
    assert body["is_draft"] is True
    assert "Ley Estatutaria 1581" in body["text"]
    assert body["version"].startswith("borrador-")
    assert len(body["sha256"]) == 64


def test_upload_requires_consent(api: ApiHarness, tenant_sin_consent: Tenant) -> None:
    assert _upload(api, tenant_sin_consent) == 403
    assert api.storage.objects == {}
    assert api.enqueued == []


def test_accept_consent_then_upload(
    api: ApiHarness, owner_engine: Engine, tenant_sin_consent: Tenant
) -> None:
    t = tenant_sin_consent
    version = api.client.get("/consent", headers=t.headers).json()["version"]

    r = api.client.post("/consent", headers=t.headers, json={"version": "otra-version"})
    assert r.status_code == 409

    r = api.client.post("/consent", headers=t.headers, json={"version": version})
    assert r.status_code == 201, r.text
    assert r.json()["accepted"] is True
    assert r.json()["accepted_at"] is not None
    # Aceptar dos veces no duplica la fila ni el evento.
    assert api.client.post("/consent", headers=t.headers, json={"version": version}).is_success

    with Session(owner_engine) as s:
        rows = list(s.scalars(select(DataUseConsent).where(DataUseConsent.user_id == t.user_id)))
        assert len(rows) == 1
        assert rows[0].version == version
        assert rows[0].organization_id == t.org_id
        events = list(
            s.scalars(
                select(AuditEvent).where(
                    AuditEvent.organization_id == t.org_id,
                    AuditEvent.action == "consent.accepted",
                )
            )
        )
        assert len(events) == 1
        assert events[0].actor == f"user:{t.user_id}"
        assert events[0].new_value == {"version": version, "text_sha256": rows[0].text_sha256}

    assert _upload(api, t) == 201


def test_consent_of_other_org_does_not_count(
    api: ApiHarness, tenant_a: Tenant, tenant_sin_consent: Tenant
) -> None:
    # El usuario de tenant_a aceptó, pero en su organización; con otra organización no vale.
    headers = {
        "X-User-Id": str(tenant_a.user_id),
        "X-Organization-Id": str(tenant_sin_consent.org_id),
    }
    assert api.client.get("/consent", headers=headers).status_code == 401


def test_delete_document(api: ApiHarness, owner_engine: Engine, tenant_a: Tenant) -> None:
    r = api.client.post(
        "/documents", files=[("files", ("f.pdf", PDF, "application/pdf"))], headers=tenant_a.headers
    )
    doc_id = r.json()[0]["id"]
    assert len(api.storage.objects) == 1

    r = api.client.delete(f"/documents/{doc_id}", headers=tenant_a.headers)
    assert r.status_code == 204
    assert api.storage.objects == {}
    assert api.client.get(f"/documents/{doc_id}", headers=tenant_a.headers).status_code == 404
    with Session(owner_engine) as s:
        assert s.get(Document, uuid.UUID(doc_id)) is None
        actions = list(s.scalars(select(AuditEvent.action).where(AuditEvent.entity_id == doc_id)))
    assert sorted(actions) == ["document.deleted", "document.uploaded"]


def test_delete_cascades_and_keeps_llm_cost(
    api: ApiHarness, owner_engine: Engine, tenant_a: Tenant
) -> None:
    key = f"org/{tenant_a.org_id}/documents/{tenant_a.document_id}.pdf"
    api.storage.objects[key] = (PDF, "application/pdf")
    r = api.client.delete(f"/documents/{tenant_a.document_id}", headers=tenant_a.headers)
    assert r.status_code == 204, r.text
    assert key not in api.storage.objects
    with Session(owner_engine) as s:
        assert s.get(Extraction, tenant_a.extraction_id) is None
        assert s.get(ExtractedField, tenant_a.field_id) is None
        calls = list(s.scalars(select(LlmCall).where(LlmCall.organization_id == tenant_a.org_id)))
        assert len(calls) == 1
        assert calls[0].document_id is None
        event = s.scalars(
            select(AuditEvent).where(
                AuditEvent.entity_id == str(tenant_a.document_id),
                AuditEvent.action == "document.deleted",
            )
        ).one()
        assert event.actor == f"user:{tenant_a.user_id}"
        assert event.old_value is not None
        assert "filename" not in event.old_value
        # El evento de carga anterior (semilla) sigue: audit_events es inmutable.
        assert s.scalars(
            select(AuditEvent).where(
                AuditEvent.entity_id == str(tenant_a.document_id), AuditEvent.action == "seed"
            )
        ).one()


def test_cannot_delete_other_org_document(
    api: ApiHarness, owner_engine: Engine, tenant_a: Tenant, tenant_b: Tenant
) -> None:
    r = api.client.delete(f"/documents/{tenant_b.document_id}", headers=tenant_a.headers)
    assert r.status_code == 404
    with Session(owner_engine) as s:
        assert s.get(Document, tenant_b.document_id) is not None


def test_delete_storage_failure_keeps_rows(
    api: ApiHarness, owner_engine: Engine, tenant_a: Tenant
) -> None:
    def broken_delete(key: str) -> None:
        raise ConnectionError("almacenamiento caído")

    api.storage.delete = broken_delete  # type: ignore[method-assign]
    r = api.client.delete(f"/documents/{tenant_a.document_id}", headers=tenant_a.headers)
    assert r.status_code == 502
    with Session(owner_engine) as s:
        assert s.get(Document, tenant_a.document_id) is not None
        assert (
            s.scalars(
                select(AuditEvent).where(
                    AuditEvent.entity_id == str(tenant_a.document_id),
                    AuditEvent.action == "document.deleted",
                )
            ).first()
            is None
        )
