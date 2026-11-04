"""Aislamiento entre organizaciones con el rol `contable_app` (regla dura 6)."""

import uuid

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AuditEvent,
    Document,
    ExtractedField,
    Extraction,
    LlmCall,
    Organization,
    User,
)
from app.db.session import tenant_session
from tests.conftest import ApiHarness, Tenant

MODELS = (Organization, User, Document, Extraction, ExtractedField, LlmCall, AuditEvent)


def test_connected_as_app_role(app_factory: sessionmaker[Session]) -> None:
    with app_factory() as s:
        assert s.execute(text("SELECT current_user")).scalar_one() == "contable_app"


def test_org_sees_only_its_rows(
    app_factory: sessionmaker[Session], tenant_a: Tenant, tenant_b: Tenant
) -> None:
    with tenant_session(tenant_a.org_id, app_factory) as s:
        for model in MODELS:
            column = "id" if model is Organization else "organization_id"
            orgs = set(s.scalars(select(getattr(model, column)).distinct()))
            assert orgs == {tenant_a.org_id}, model.__tablename__
        assert s.get(Document, tenant_b.document_id) is None
        assert s.get(ExtractedField, tenant_b.field_id) is None
        assert s.get(Document, tenant_a.document_id) is not None
        assert s.get(ExtractedField, tenant_a.field_id) is not None


def test_without_context_sees_nothing(app_factory: sessionmaker[Session], tenant_a: Tenant) -> None:
    with app_factory() as s:
        for model in MODELS:
            assert s.scalar(select(func.count()).select_from(model)) == 0, model.__tablename__


def test_cannot_insert_into_other_org(
    app_factory: sessionmaker[Session], tenant_a: Tenant, tenant_b: Tenant
) -> None:
    with tenant_session(tenant_a.org_id, app_factory) as s:
        s.add(
            AuditEvent(
                organization_id=tenant_b.org_id,
                actor="user:intruso",
                action="x",
                entity="documents",
                entity_id=str(tenant_b.document_id),
            )
        )
        with pytest.raises(ProgrammingError, match="row-level security"):
            s.flush()


def test_cannot_update_other_org(
    app_factory: sessionmaker[Session], tenant_a: Tenant, tenant_b: Tenant
) -> None:
    with tenant_session(tenant_a.org_id, app_factory) as s:
        result = s.execute(
            update(ExtractedField)
            .where(ExtractedField.id == tenant_b.field_id)
            .values(corrected_value="hackeado")
        )
        assert result.rowcount == 0  # type: ignore[attr-defined]
        s.commit()
    with tenant_session(tenant_b.org_id, app_factory) as s:
        field = s.get(ExtractedField, tenant_b.field_id)
        assert field is not None
        assert field.corrected_value is None


def test_context_does_not_leak_between_transactions(
    app_factory: sessionmaker[Session], tenant_a: Tenant
) -> None:
    # Misma conexión del pool: tras el commit, una sesión sin organización no ve nada.
    with tenant_session(tenant_a.org_id, app_factory) as s:
        assert s.get(Document, tenant_a.document_id) is not None
        s.commit()
    with app_factory() as s:
        assert s.scalar(select(func.count()).select_from(Document)) == 0


def test_api_hides_other_org_document(api: ApiHarness, tenant_a: Tenant, tenant_b: Tenant) -> None:
    r = api.client.get(f"/documents/{tenant_b.document_id}", headers=tenant_a.headers)
    assert r.status_code == 404
    listed = api.client.get("/documents", headers=tenant_a.headers).json()
    assert {d["id"] for d in listed} == {str(tenant_a.document_id)}


def test_api_cannot_patch_other_org_field(
    api: ApiHarness, tenant_a: Tenant, tenant_b: Tenant
) -> None:
    r = api.client.patch(
        f"/fields/{tenant_b.field_id}", json={"corrected_value": "x"}, headers=tenant_a.headers
    )
    assert r.status_code == 404


def test_api_rejects_user_from_other_org(
    api: ApiHarness, tenant_a: Tenant, tenant_b: Tenant
) -> None:
    headers = {"X-User-Id": str(tenant_b.user_id), "X-Organization-Id": str(tenant_a.org_id)}
    assert api.client.get("/documents", headers=headers).status_code == 401


def test_api_requires_auth_headers(api: ApiHarness) -> None:
    assert api.client.get("/documents").status_code == 401
    headers = {"X-User-Id": str(uuid.uuid4()), "X-Organization-Id": str(uuid.uuid4())}
    assert api.client.get("/documents", headers=headers).status_code == 401
