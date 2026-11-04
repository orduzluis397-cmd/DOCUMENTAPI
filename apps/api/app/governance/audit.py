"""Escritura de `audit_events` (regla dura 5).

`record` solo AÑADE el evento a la sesión: lo persiste el mismo commit que el cambio auditado.
Si el commit falla, no queda ni el cambio ni el evento.
"""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AuditEvent


def record(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor: str,
    action: str,
    entity: str,
    entity_id: uuid.UUID | str,
    old_value: Any = None,
    new_value: Any = None,
    model: str | None = None,
    prompt_version: str | None = None,
    trace_id: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        organization_id=organization_id,
        actor=actor,
        action=action,
        entity=entity,
        entity_id=str(entity_id),
        old_value=old_value,
        new_value=new_value,
        model=model,
        prompt_version=prompt_version,
        trace_id=trace_id,
    )
    session.add(event)
    return event
