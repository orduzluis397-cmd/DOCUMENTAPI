"""Verificación de los tokens de sesión de Clerk (JWT RS256 firmados con las JWKS de la app).

Se comprueba: firma con una clave de las JWKS (caché en memoria, se refresca si llega un `kid`
nuevo), algoritmo RS256, `exp`/`nbf`/`iat` con una holgura corta, `iss` igual al emisor
configurado, `azp` dentro de los orígenes autorizados y, si se configuró, `aud`. Se aceptan los
claims de organización de la versión 2 del token (`o.id`, `o.rol`, `o.slg`) y de la 1
(`org_id`, `org_role`, `org_slug`).

Documentación: https://clerk.com/docs/backend-requests/manual-jwt y
https://clerk.com/docs/backend-requests/resources/session-tokens (consultadas el 2026-11-04).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import jwt
from jwt import PyJWK, PyJWKClient

ALGORITHMS = ["RS256"]


class ClerkAuthError(Exception):
    """Token rechazado. `status_code` es 401 (token inválido) o 403 (sin permiso)."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class SigningKeySource(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> PyJWK: ...


@dataclass(frozen=True, slots=True)
class ClerkIdentity:
    """Lo que la API necesita del token ya verificado."""

    user_external_id: str
    org_external_id: str | None
    org_role: str | None = None
    org_slug: str | None = None
    org_name: str | None = None
    email: str | None = None
    full_name: str | None = None


def _str_claim(claims: dict[str, Any], name: str) -> str | None:
    value = claims.get(name)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _org_claims(claims: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    org = claims.get("o")
    if isinstance(org, dict):  # versión 2
        org_id = org.get("id")
        role = org.get("rol")
        slug = org.get("slg")
        return (
            org_id if isinstance(org_id, str) and org_id else None,
            role if isinstance(role, str) else None,
            slug if isinstance(slug, str) else None,
        )
    return (
        _str_claim(claims, "org_id"),
        _str_claim(claims, "org_role"),
        _str_claim(claims, "org_slug"),
    )


class ClerkVerifier:
    def __init__(
        self,
        *,
        issuer: str,
        keys: SigningKeySource,
        authorized_parties: list[str],
        audience: str | None = None,
        leeway_s: int = 5,
    ) -> None:
        self._issuer = issuer.rstrip("/")
        self._keys = keys
        self._authorized_parties = frozenset(p.rstrip("/") for p in authorized_parties)
        self._audience = audience
        self._leeway = leeway_s

    @classmethod
    def from_jwks_url(
        cls,
        *,
        issuer: str,
        jwks_url: str,
        authorized_parties: list[str],
        audience: str | None = None,
        leeway_s: int = 5,
        cache_s: int = 3600,
    ) -> ClerkVerifier:
        client = PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=cache_s, timeout=10)
        return cls(
            issuer=issuer,
            keys=client,
            authorized_parties=authorized_parties,
            audience=audience,
            leeway_s=leeway_s,
        )

    def verify(self, token: str) -> ClerkIdentity:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise ClerkAuthError(401, "Token mal formado.") from exc
        if header.get("alg") not in ALGORITHMS:
            raise ClerkAuthError(401, "Algoritmo de firma no permitido.")
        try:
            key = self._keys.get_signing_key_from_jwt(token)
        except jwt.PyJWTError as exc:
            raise ClerkAuthError(401, "No se encontró la clave de firma del token.") from exc
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key.key,
                algorithms=ALGORITHMS,
                issuer=self._issuer,
                audience=self._audience,
                leeway=self._leeway,
                options={
                    "require": ["exp", "iat", "iss", "sub"],
                    "verify_aud": self._audience is not None,
                },
            )
        except jwt.ExpiredSignatureError as exc:
            raise ClerkAuthError(401, "La sesión venció. Vuelve a entrar.") from exc
        except jwt.InvalidIssuerError as exc:
            raise ClerkAuthError(401, "Emisor del token no válido.") from exc
        except jwt.PyJWTError as exc:
            raise ClerkAuthError(401, "Token no válido.") from exc

        if self._authorized_parties:
            azp = _str_claim(claims, "azp")
            if azp is None or azp.rstrip("/") not in self._authorized_parties:
                raise ClerkAuthError(401, "Origen del token no autorizado.")

        status = _str_claim(claims, "sts")
        if status is not None and status != "active":
            raise ClerkAuthError(403, "La sesión no está activa (¿falta elegir organización?).")

        sub = _str_claim(claims, "sub")
        if sub is None:
            raise ClerkAuthError(401, "Token sin usuario.")
        org_id, org_role, org_slug = _org_claims(claims)
        return ClerkIdentity(
            user_external_id=sub,
            org_external_id=org_id,
            org_role=org_role,
            org_slug=org_slug,
            # Claims personalizados opcionales (ver docs/deploy/GUIA-DESPLIEGUE.md).
            org_name=_str_claim(claims, "org_name"),
            email=_str_claim(claims, "email"),
            full_name=_str_claim(claims, "name"),
        )
