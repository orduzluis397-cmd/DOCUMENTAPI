"""Autenticación: tokens de Clerk en la demo; stub por cabeceras SOLO en local/test.

- `AUTH_PROVIDER=clerk`: la web manda `Authorization: Bearer <token de sesión de Clerk>`. Se
  verifica el JWT (app/clerk.py) y se mapea `sub` → `users.external_auth_id` y la organización
  activa (`o.id` / `org_id`) → `organizations.external_auth_id`. Sin organización activa → 403.
- `AUTH_PROVIDER=stub` (solo `APP_ENV=local|test`): usuario y organización en las cabeceras
  `X-User-Id` y `X-Organization-Id`. Fuera de esos entornos el stub se rechaza al arrancar
  (app/config.py) y, por si acaso, también aquí.

Alta al primer uso, sin saltarse RLS: el UUID de la organización se deriva de su id de Clerk
(UUID v5 con un espacio de nombres fijo), así que la sesión de alta ya corre con
`app.organization_id` = esa organización y las políticas de RLS se cumplen sin ningún rol con
privilegios. El alta de organización y de usuario deja evento en `audit_events` en la misma
transacción. Las carreras (dos peticiones a la vez) se resuelven con `ON CONFLICT DO NOTHING`.
"""

import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from app.clerk import ClerkAuthError, ClerkIdentity, ClerkVerifier
from app.config import STUB_AUTH_ENVS, Settings, get_settings
from app.db.models import Organization, User
from app.db.session import get_sessionmaker, tenant_session
from app.governance import audit

STUB_ENVS = STUB_AUTH_ENVS
# Espacio de nombres fijo para derivar el UUID de una organización de Clerk. NO cambiarlo:
# cambiaría el UUID de todas las organizaciones ya creadas.
CLERK_ORG_NAMESPACE = uuid.UUID("6f1c6d3e-2a52-5b8e-9d1e-0c4a1e7b9f10")
AUTH_ACTOR = "system:auth"
_PLACEHOLDER_EMAIL_DOMAIN = "clerk.invalid"


@dataclass(frozen=True, slots=True)
class Principal:
    """Quién hace la petición y en nombre de qué organización."""

    user_id: uuid.UUID
    organization_id: uuid.UUID

    @property
    def actor(self) -> str:
        """Identificador del actor para `audit_events`."""
        return f"user:{self.user_id}"


def get_session_factory() -> sessionmaker[Session]:
    return get_sessionmaker()


@lru_cache(maxsize=4)
def _build_verifier(
    issuer: str,
    jwks_url: str,
    parties: tuple[str, ...],
    audience: str | None,
    leeway_s: int,
    cache_s: int,
) -> ClerkVerifier:
    # Un verificador (y su caché de JWKS) por configuración y proceso.
    return ClerkVerifier.from_jwks_url(
        issuer=issuer,
        jwks_url=jwks_url,
        authorized_parties=list(parties),
        audience=audience,
        leeway_s=leeway_s,
        cache_s=cache_s,
    )


def get_clerk_verifier(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClerkVerifier | None:
    """Verificador de Clerk, o None con el stub. Las pruebas lo sustituyen (JWKS falsas)."""
    if settings.auth_provider != "clerk":
        return None
    jwks = settings.clerk_jwks_endpoint
    if not settings.clerk_issuer or not jwks:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Autenticación no configurada (CLERK_ISSUER)."
        )
    return _build_verifier(
        settings.clerk_issuer,
        jwks,
        tuple(settings.clerk_authorized_party_list),
        settings.clerk_audience,
        settings.clerk_leeway_s,
        settings.clerk_jwks_cache_s,
    )


def organization_uuid(org_external_id: str) -> uuid.UUID:
    return uuid.uuid5(CLERK_ORG_NAMESPACE, f"clerk:{org_external_id}")


def _role(identity: ClerkIdentity) -> str:
    role = (identity.org_role or "").removeprefix("org:")
    return "admin" if role == "admin" else "member"


def provision_principal(factory: sessionmaker[Session], identity: ClerkIdentity) -> Principal:
    """Devuelve el `Principal` del token; crea organización y usuario la primera vez."""
    if identity.org_external_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Selecciona o crea una organización para usar Contable IA.",
        )
    org_ext = identity.org_external_id
    org_id = organization_uuid(org_ext)
    with tenant_session(org_id, factory) as s:
        created_org = s.scalar(
            pg_insert(Organization)
            .values(
                id=org_id,
                name=(identity.org_name or identity.org_slug or org_ext)[:200],
                external_auth_id=org_ext,
            )
            .on_conflict_do_nothing()
            .returning(Organization.id)
        )
        org_ext_stored = s.scalar(
            select(Organization.external_auth_id).where(Organization.id == org_id)
        )
        if org_ext_stored != org_ext:
            # Solo pasaría si alguien creó a mano una fila con ese UUID: no se mezcla.
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Organización inconsistente.")
        if created_org is not None:
            audit.record(
                s,
                organization_id=org_id,
                actor=AUTH_ACTOR,
                action="organization.provisioned",
                entity="organizations",
                entity_id=org_id,
                new_value={"provider": "clerk", "external_auth_id": org_ext},
            )

        sub = identity.user_external_id
        user_id = s.scalar(select(User.id).where(User.external_auth_id == sub))
        if user_id is None:
            email = identity.email or f"{sub}@{_PLACEHOLDER_EMAIL_DOMAIN}"
            user_id = s.scalar(
                pg_insert(User)
                .values(
                    id=uuid.uuid4(),
                    organization_id=org_id,
                    email=email[:320],
                    full_name=(identity.full_name or None) and identity.full_name[:200],
                    role=_role(identity),
                    external_auth_id=sub,
                )
                .on_conflict_do_nothing()
                .returning(User.id)
            )
            if user_id is not None:
                audit.record(
                    s,
                    organization_id=org_id,
                    actor=AUTH_ACTOR,
                    action="user.provisioned",
                    entity="users",
                    entity_id=user_id,
                    new_value={
                        "provider": "clerk",
                        "external_auth_id": sub,
                        "role": _role(identity),
                    },
                )
            else:
                # Otra petición lo creó a la vez, o el correo ya existe con otro usuario de Clerk.
                user_id = s.scalar(select(User.id).where(User.external_auth_id == sub))
                if user_id is None:
                    raise HTTPException(
                        status.HTTP_409_CONFLICT,
                        "Ya existe otro usuario con ese correo en la organización.",
                    )
        s.commit()
    return Principal(user_id=user_id, organization_id=org_id)


def _bearer(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Falta el token de sesión.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Cabecera Authorization no válida.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token.strip()


def get_principal(
    settings: Annotated[Settings, Depends(get_settings)],
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
    verifier: Annotated[ClerkVerifier | None, Depends(get_clerk_verifier)],
    authorization: Annotated[str | None, Header()] = None,
    x_user_id: Annotated[uuid.UUID | None, Header()] = None,
    x_organization_id: Annotated[uuid.UUID | None, Header()] = None,
) -> Principal:
    if settings.auth_provider == "clerk":
        if verifier is None:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Autenticación no configurada."
            )
        try:
            identity = verifier.verify(_bearer(authorization))
        except ClerkAuthError as exc:
            raise HTTPException(
                exc.status_code, exc.detail, headers={"WWW-Authenticate": "Bearer"}
            ) from exc
        return provision_principal(factory, identity)

    if settings.app_env not in STUB_ENVS:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="El stub de autenticación solo funciona en local/test.",
        )
    if x_user_id is None or x_organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Faltan las cabeceras X-User-Id y X-Organization-Id (stub de desarrollo).",
        )
    return Principal(user_id=x_user_id, organization_id=x_organization_id)
