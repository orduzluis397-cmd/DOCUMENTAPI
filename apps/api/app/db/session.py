"""Motor y sesiones de base de datos con contexto de organización para RLS.

Cada transacción que abre una sesión de inquilino ejecuta
`set_config('app.organization_id', <org>, true)` (alcance de transacción), así que el valor
nunca se filtra a otra petición que reutilice la conexión del pool. Las políticas de RLS de la
migración comparan `organization_id` con ese valor; sin él, el rol de la app no ve ninguna fila.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, SessionTransaction, sessionmaker

from app.config import get_settings

ORG_SETTING = "app.organization_id"
_ORG_KEY = "organization_id"


@lru_cache
def get_engine() -> Engine:
    """Motor de la app (rol `contable_app`, sin BYPASSRLS)."""
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    # expire_on_commit=False: tras el commit los objetos siguen legibles sin otra consulta
    # (que ya no tendría el contexto de organización de la transacción anterior).
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


@event.listens_for(Session, "after_begin")
def _set_tenant_context(session: Session, transaction: SessionTransaction, connection: Any) -> None:
    org_id = session.info.get(_ORG_KEY)
    if org_id is not None:
        connection.execute(
            text("SELECT set_config(:name, :value, true)"),
            {"name": ORG_SETTING, "value": str(org_id)},
        )


def bind_organization(session: Session, organization_id: uuid.UUID) -> None:
    """Fija la organización de la sesión. Debe llamarse antes de la primera consulta."""
    if session.in_transaction():
        raise RuntimeError("La organización debe fijarse antes de abrir la transacción")
    session.info[_ORG_KEY] = organization_id


@contextmanager
def tenant_session(
    organization_id: uuid.UUID, factory: sessionmaker[Session] | None = None
) -> Iterator[Session]:
    """Sesión limitada a una organización; rollback si hay excepción. El commit es explícito."""
    session = (factory or get_sessionmaker())()
    try:
        bind_organization(session, organization_id)
        yield session
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
