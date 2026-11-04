"""Carga, listado, detalle y archivo de documentos; paso `queued` → `processing` del worker."""

import uuid

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db.models import AuditEvent, Document
from app.files import sniff
from app.main import app
from app.workers.tasks import claim_document
from tests.conftest import ApiHarness, Tenant

PDF = b"%PDF-1.7\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
XML = b'<?xml version="1.0" encoding="UTF-8"?><Invoice xmlns="urn:oasis"></Invoice>'


def test_sniff_detects_real_type() -> None:
    assert sniff(PDF) == "application/pdf"
    assert sniff(PNG) == "image/png"
    assert sniff(b"\xff\xd8\xff\xe0" + b"\x00" * 8) == "image/jpeg"
    assert sniff(b"II*\x00rest") == "image/tiff"
    assert sniff(XML) == "application/xml"
    assert sniff(b"PK\x03\x04resto-del-zip") == "application/zip"
    assert sniff(b"\xef\xbb\xbf<Invoice/>") == "application/xml"
    assert sniff(b"MZ\x90\x00 ejecutable") is None
    assert sniff(b"texto plano") is None
    assert sniff(b"< no es xml") is None


def test_upload_multiple(api: ApiHarness, owner_engine: Engine, tenant_a: Tenant) -> None:
    r = api.client.post(
        "/documents",
        files=[
            ("files", ("factura.pdf", PDF, "application/pdf")),
            # El Content-Type del cliente se ignora: manda la firma del contenido.
            ("files", ("../../escaneo.bin", PNG, "application/octet-stream")),
        ],
        headers=tenant_a.headers,
    )
    assert r.status_code == 201, r.text
    docs = r.json()
    assert [d["filename"] for d in docs] == ["factura.pdf", "escaneo.bin"]
    assert [d["content_type"] for d in docs] == ["application/pdf", "image/png"]
    assert all(d["status"] == "queued" for d in docs)

    ids = [uuid.UUID(d["id"]) for d in docs]
    assert api.enqueued == [(i, tenant_a.org_id) for i in ids]
    assert len(api.storage.objects) == 2
    assert all(k.startswith(f"org/{tenant_a.org_id}/") for k in api.storage.objects)

    with Session(owner_engine) as s:
        rows = list(s.scalars(select(Document).where(Document.id.in_(ids))))
        assert {row.organization_id for row in rows} == {tenant_a.org_id}
        assert {row.uploaded_by for row in rows} == {tenant_a.user_id}
        events = list(
            s.scalars(select(AuditEvent).where(AuditEvent.entity_id.in_([str(i) for i in ids])))
        )
        assert {e.action for e in events} == {"document.uploaded"}
        assert len(events) == 2


def test_upload_rejects_disallowed_type(api: ApiHarness, tenant_a: Tenant) -> None:
    r = api.client.post(
        "/documents",
        files=[
            ("files", ("ok.pdf", PDF, "application/pdf")),
            ("files", ("virus.pdf", b"MZ\x90\x00", "application/pdf")),
        ],
        headers=tenant_a.headers,
    )
    assert r.status_code == 422
    assert "virus.pdf" in r.json()["detail"]
    # Todo o nada: no se subió ni el archivo válido.
    assert api.storage.objects == {}
    assert api.enqueued == []


def test_upload_rejects_too_large(api: ApiHarness, tenant_a: Tenant) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(upload_max_bytes=len(PDF) - 1)
    r = api.client.post(
        "/documents",
        files=[("files", ("grande.pdf", PDF, "application/pdf"))],
        headers=tenant_a.headers,
    )
    assert r.status_code == 413
    assert api.storage.objects == {}


def test_upload_rejects_empty(api: ApiHarness, tenant_a: Tenant) -> None:
    r = api.client.post(
        "/documents",
        files=[("files", ("vacio.pdf", b"", "application/pdf"))],
        headers=tenant_a.headers,
    )
    assert r.status_code == 422


def test_get_detail_list_and_file(api: ApiHarness, tenant_a: Tenant) -> None:
    up = api.client.post(
        "/documents",
        files=[("files", ("f.pdf", PDF, "application/pdf"))],
        headers=tenant_a.headers,
    )
    new_id = up.json()[0]["id"]

    listed = api.client.get("/documents", headers=tenant_a.headers).json()
    assert {d["id"] for d in listed} == {new_id, str(tenant_a.document_id)}

    detail = api.client.get(f"/documents/{tenant_a.document_id}", headers=tenant_a.headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["extraction"]["id"] == str(tenant_a.extraction_id)
    by_name = {f["name"]: f for f in body["fields"]}
    assert by_name["totales.total"]["is_doubtful"] is True
    assert by_name["factura.numero"]["is_doubtful"] is False

    empty = api.client.get(f"/documents/{new_id}", headers=tenant_a.headers).json()
    assert empty["extraction"] is None
    assert empty["fields"] == []

    f = api.client.get(f"/documents/{new_id}/file", headers=tenant_a.headers)
    assert f.status_code == 200
    assert f.content == PDF
    assert f.headers["content-type"] == "application/pdf"


def test_worker_marks_processing(
    api: ApiHarness, app_factory: sessionmaker[Session], tenant_a: Tenant, tenant_b: Tenant
) -> None:
    up = api.client.post(
        "/documents",
        files=[("files", ("f.pdf", PDF, "application/pdf"))],
        headers=tenant_a.headers,
    )
    doc_id = uuid.UUID(up.json()[0]["id"])

    # Con otra organización, el worker no encuentra el documento (RLS también en el worker).
    assert claim_document(doc_id, tenant_b.org_id, app_factory) is None
    claim = claim_document(doc_id, tenant_a.org_id, app_factory)
    assert claim is not None
    assert (claim.status, claim.claimed) == ("processing", True)
    status = api.client.get(f"/documents/{doc_id}", headers=tenant_a.headers).json()["status"]
    assert status == "processing"
    # Un segundo worker no lo reclama mientras el lease está vigente.
    again = claim_document(doc_id, tenant_a.org_id, app_factory)
    assert again is not None
    assert (again.status, again.claimed) == ("processing", False)
