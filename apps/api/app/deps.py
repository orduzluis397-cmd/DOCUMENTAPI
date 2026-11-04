"""Dependencias de FastAPI: sesión de BD con contexto RLS, almacenamiento y cola."""

import uuid
from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import Principal, get_principal
from app.db.models import User
from app.db.session import get_sessionmaker, tenant_session
from app.storage import ObjectStorage, get_storage
from app.workers.tasks import process_document

EnqueueFn = Callable[[uuid.UUID, uuid.UUID], None]


def get_session_factory() -> sessionmaker[Session]:
    return get_sessionmaker()


def get_db(
    principal: Annotated[Principal, Depends(get_principal)],
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> Iterator[Session]:
    """Sesión limitada a la organización del usuario. El commit lo hace cada endpoint."""
    with tenant_session(principal.organization_id, factory) as session:
        # Con RLS, el usuario solo se encuentra si pertenece a la organización de la cabecera.
        user_id = session.scalar(select(User.id).where(User.id == principal.user_id))
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario desconocido en esta organización.",
            )
        yield session


def _celery_enqueue(document_id: uuid.UUID, organization_id: uuid.UUID) -> None:
    process_document.delay(str(document_id), str(organization_id))


def get_enqueue() -> EnqueueFn:
    return _celery_enqueue


DbSession = Annotated[Session, Depends(get_db)]
CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
Storage = Annotated[ObjectStorage, Depends(get_storage)]
Enqueue = Annotated[EnqueueFn, Depends(get_enqueue)]
