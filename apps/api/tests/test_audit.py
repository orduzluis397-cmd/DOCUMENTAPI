"""Auditoría inmutable y escrita en la misma transacción que la corrección (regla dura 5)."""

from typing import Any

import pytest
from sqlalchemy import Engine, delete, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AuditEvent, ExtractedField
from app.db.session import tenant_session
from app.governance import audit
from tests.conftest import ApiHarness, Tenant


def _events(owner_engine: Engine, entity_id: Any) -> list[AuditEvent]:
    with Session(owner_engine) as s:
        return list(
            s.scalars(
                select(AuditEvent)
                .where(AuditEvent.entity_id == str(entity_id))
                .order_by(AuditEvent.id)
            )
        )


def test_app_role_cannot_update_audit(app_factory: sessionmaker[Session], tenant_a: Tenant) -> None:
    with tenant_session(tenant_a.org_id, app_factory) as s:
        with pytest.raises(DBAPIError, match="permission denied"):
            s.execute(update(AuditEvent).values(action="borrado"))
        s.rollback()


def test_app_role_cannot_delete_audit(app_factory: sessionmaker[Session], tenant_a: Tenant) -> None:
    with tenant_session(tenant_a.org_id, app_factory) as s:
        with pytest.raises(DBAPIError, match="permission denied"):
            s.execute(delete(AuditEvent))
        s.rollback()


def test_app_role_cannot_truncate_audit(
    app_factory: sessionmaker[Session], tenant_a: Tenant
) -> None:
    with tenant_session(tenant_a.org_id, app_factory) as s:
        with pytest.raises(DBAPIError, match="permission denied"):
            s.execute(text("TRUNCATE audit_events"))
        s.rollback()


def test_trigger_blocks_even_the_owner(owner_engine: Engine, tenant_a: Tenant) -> None:
    with owner_engine.connect() as conn:
        with pytest.raises(DBAPIError, match="inmutable"):
            conn.execute(update(AuditEvent).values(action="borrado"))
        conn.rollback()
        with pytest.raises(DBAPIError, match="inmutable"):
            conn.execute(delete(AuditEvent))
        conn.rollback()


def test_patch_writes_field_and_audit(
    api: ApiHarness, owner_engine: Engine, tenant_a: Tenant
) -> None:
    r = api.client.patch(
        f"/fields/{tenant_a.doubtful_field_id}",
        json={"corrected_value": 1190000},
        headers=tenant_a.headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["corrected_value"] == 1190000
    assert body["value"] == 1000
    assert body["corrected_by"] == str(tenant_a.user_id)

    events = _events(owner_engine, tenant_a.doubtful_field_id)
    assert len(events) == 1
    ev = events[0]
    assert ev.organization_id == tenant_a.org_id
    assert ev.actor == f"user:{tenant_a.user_id}"
    assert ev.action == "field.corrected"
    assert ev.entity == "extracted_fields"
    assert ev.old_value == {"value": 1000, "corrected_value": None}
    assert ev.new_value == {"corrected_value": 1190000, "name": "totales.total"}
    assert ev.model == "modelo-x"
    assert ev.prompt_version == "v1"
    assert ev.trace_id == "trace-org-a"
    assert ev.occurred_at is not None


def test_patch_rolls_back_field_if_audit_fails(
    api: ApiHarness,
    owner_engine: Engine,
    tenant_a: Tenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_record = audit.record

    def broken_record(session: Session, **kwargs: Any) -> AuditEvent:
        # El evento no cumple NOT NULL: falla al hacer flush, en la misma transacción.
        event = real_record(session, **kwargs)
        event.action = None  # type: ignore[assignment]
        return event

    monkeypatch.setattr(audit, "record", broken_record)

    r = api.client.patch(
        f"/fields/{tenant_a.field_id}",
        json={"corrected_value": "FE-999"},
        headers=tenant_a.headers,
    )
    assert r.status_code == 500

    with Session(owner_engine) as s:
        field = s.get(ExtractedField, tenant_a.field_id)
        assert field is not None
        assert field.corrected_value is None
        assert field.corrected_by is None
        assert field.corrected_at is None
    assert _events(owner_engine, tenant_a.field_id) == []


def test_patch_validates_body(api: ApiHarness, tenant_a: Tenant) -> None:
    r = api.client.patch(f"/fields/{tenant_a.field_id}", json={"otro": 1}, headers=tenant_a.headers)
    assert r.status_code == 422
