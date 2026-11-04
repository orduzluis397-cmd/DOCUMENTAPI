"""Autenticación — STUB de desarrollo, aislado aquí para cambiarlo por Clerk/Auth.js.

PENDIENTE (F0-13 / despliegue): reemplazar `get_principal` por la verificación del token del
proveedor (JWT de Clerk o sesión de Auth.js) y mapear `external_auth_id` → `users`. El resto de
la API solo depende de `Principal` y de `get_principal`, así que el cambio queda en este módulo.

Mientras tanto, en `APP_ENV=local|test`, el usuario y la organización llegan en las cabeceras
`X-User-Id` y `X-Organization-Id`. En cualquier otro entorno el stub rechaza la petición, para que
nunca llegue a producción por descuido.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.config import Settings, get_settings

STUB_ENVS = frozenset({"local", "test"})


@dataclass(frozen=True, slots=True)
class Principal:
    """Quién hace la petición y en nombre de qué organización."""

    user_id: uuid.UUID
    organization_id: uuid.UUID

    @property
    def actor(self) -> str:
        """Identificador del actor para `audit_events`."""
        return f"user:{self.user_id}"


def get_principal(
    settings: Annotated[Settings, Depends(get_settings)],
    x_user_id: Annotated[uuid.UUID | None, Header()] = None,
    x_organization_id: Annotated[uuid.UUID | None, Header()] = None,
) -> Principal:
    if settings.app_env not in STUB_ENVS:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Autenticación real pendiente (Clerk/Auth.js); el stub solo funciona en local.",
        )
    if x_user_id is None or x_organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Faltan las cabeceras X-User-Id y X-Organization-Id (stub de desarrollo).",
        )
    return Principal(user_id=x_user_id, organization_id=x_organization_id)
