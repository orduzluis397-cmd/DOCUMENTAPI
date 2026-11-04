"""Autenticación con Clerk: verificación del JWT con JWKS falsas (sin red) y alta al primer uso."""

import json
import time
import uuid
from collections.abc import Iterator
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt import PyJWKClient
from jwt.algorithms import RSAAlgorithm
from pydantic import ValidationError
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.auth import get_clerk_verifier, organization_uuid
from app.clerk import ClerkAuthError, ClerkVerifier
from app.config import Settings, get_settings
from app.db.models import AuditEvent, Organization, User
from app.deps import get_enqueue
from app.main import app
from app.storage import get_storage
from tests.conftest import FakeStorage

ISSUER = "https://demo-app.clerk.accounts.dev"
WEB = "https://contable-ia-demo.vercel.app"
KID = "kid-prueba-1"


def _key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


SIGNING_KEY = _key()
OTHER_KEY = _key()


def _jwks(key: rsa.RSAPrivateKey, kid: str = KID) -> dict[str, Any]:
    jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return {"keys": [jwk]}


class FakeJwksClient(PyJWKClient):
    """PyJWKClient real (con su caché) pero sin red: `fetch_data` devuelve JWKS fijas."""

    def __init__(self, jwks: dict[str, Any]) -> None:
        super().__init__(f"{ISSUER}/.well-known/jwks.json", cache_jwk_set=True, lifespan=3600)
        self._jwks = jwks
        self.fetches = 0

    def fetch_data(self) -> Any:
        self.fetches += 1
        if self.jwk_set_cache is not None:
            self.jwk_set_cache.put(self._jwks)
        return self._jwks


def make_token(
    *,
    sub: str = "user_abc",
    org: dict[str, Any] | None = None,
    key: rsa.RSAPrivateKey = SIGNING_KEY,
    kid: str = KID,
    exp_in: int = 60,
    **extra: Any,
) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "sub": sub,
        "azp": WEB,
        "iat": now - 5,
        "nbf": now - 5,
        "exp": now + exp_in,
        "sid": "sess_1",
        "v": 2,
    }
    if org is not None:
        claims["o"] = org
    claims.update(extra)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


def clerk_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "auth_provider": "clerk",
        "clerk_issuer": ISSUER,
        "clerk_authorized_parties": WEB,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def jwks_client() -> FakeJwksClient:
    return FakeJwksClient(_jwks(SIGNING_KEY))


@pytest.fixture
def verifier(jwks_client: FakeJwksClient) -> ClerkVerifier:
    return ClerkVerifier(issuer=ISSUER, keys=jwks_client, authorized_parties=[WEB])


@pytest.fixture
def clerk_api(migrated: None, verifier: ClerkVerifier) -> Iterator[TestClient]:
    settings = clerk_settings()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_clerk_verifier] = lambda: verifier
    storage = FakeStorage()
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_enqueue] = lambda: lambda _doc, _org: None
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _org() -> dict[str, Any]:
    return {"id": f"org_{uuid.uuid4().hex[:12]}", "rol": "admin", "slg": "pyme-prueba"}


# ---------------------------------------------------------------------------------------------
# Verificador (sin BD)
# ---------------------------------------------------------------------------------------------


def test_valid_token_v2(verifier: ClerkVerifier) -> None:
    org = _org()
    ident = verifier.verify(make_token(org=org, email="ana@example.com"))
    assert ident.user_external_id == "user_abc"
    assert ident.org_external_id == org["id"]
    assert ident.org_role == "admin"
    assert ident.email == "ana@example.com"


def test_valid_token_v1_org_claims(verifier: ClerkVerifier) -> None:
    ident = verifier.verify(make_token(org_id="org_v1", org_role="org:member", v=1))
    assert ident.org_external_id == "org_v1"
    assert ident.org_role == "org:member"


@pytest.mark.parametrize(
    ("token_kwargs", "detail"),
    [
        ({"exp_in": -120}, "venció"),
        ({"iss": "https://atacante.example.com"}, "Emisor"),
        ({"azp": "https://otro-sitio.example.com"}, "Origen"),
        ({"key": OTHER_KEY}, "no válido"),
        ({"kid": "kid-desconocido"}, "clave de firma"),
    ],
)
def test_rejected_tokens(
    verifier: ClerkVerifier, token_kwargs: dict[str, Any], detail: str
) -> None:
    with pytest.raises(ClerkAuthError) as exc:
        verifier.verify(make_token(org=_org(), **token_kwargs))
    assert exc.value.status_code == 401
    assert detail in exc.value.detail


def test_rejects_hs256_and_garbage(verifier: ClerkVerifier) -> None:
    hs = jwt.encode(
        {"iss": ISSUER, "sub": "user_x", "exp": int(time.time()) + 60, "iat": int(time.time())},
        "secreto-compartido-de-prueba-que-no-sirve",
        algorithm="HS256",
        headers={"kid": KID},
    )
    for token in (hs, "no-es-un-jwt"):
        with pytest.raises(ClerkAuthError) as exc:
            verifier.verify(token)
        assert exc.value.status_code == 401


def test_missing_azp_rejected(verifier: ClerkVerifier) -> None:
    token = make_token(org=_org())
    claims = jwt.decode(token, options={"verify_signature": False})
    del claims["azp"]
    no_azp = jwt.encode(claims, SIGNING_KEY, algorithm="RS256", headers={"kid": KID})
    with pytest.raises(ClerkAuthError) as exc:
        verifier.verify(no_azp)
    assert exc.value.status_code == 401


def test_audience_checked_when_configured(jwks_client: FakeJwksClient) -> None:
    v = ClerkVerifier(
        issuer=ISSUER, keys=jwks_client, authorized_parties=[WEB], audience="contable-api"
    )
    with pytest.raises(ClerkAuthError):
        v.verify(make_token(org=_org()))
    assert v.verify(make_token(org=_org(), aud="contable-api")).user_external_id == "user_abc"


def test_pending_session_forbidden(verifier: ClerkVerifier) -> None:
    with pytest.raises(ClerkAuthError) as exc:
        verifier.verify(make_token(org=_org(), sts="pending"))
    assert exc.value.status_code == 403


def test_jwks_are_cached(verifier: ClerkVerifier, jwks_client: FakeJwksClient) -> None:
    for _ in range(5):
        verifier.verify(make_token(org=_org()))
    assert jwks_client.fetches == 1


# ---------------------------------------------------------------------------------------------
# Configuración: el stub no puede llegar a un entorno desplegado
# ---------------------------------------------------------------------------------------------


def test_deployed_env_rejects_stub() -> None:
    with pytest.raises(ValidationError, match="AUTH_PROVIDER=clerk"):
        Settings(app_env="production", auth_provider="stub")


def test_deployed_env_requires_issuer_and_parties() -> None:
    with pytest.raises(ValidationError, match="CLERK_ISSUER"):
        Settings(app_env="production", auth_provider="clerk", clerk_authorized_parties=WEB)
    with pytest.raises(ValidationError, match="CLERK_AUTHORIZED_PARTIES"):
        Settings(app_env="production", auth_provider="clerk", clerk_issuer=ISSUER)
    ok = Settings(
        app_env="production",
        auth_provider="clerk",
        clerk_issuer=ISSUER,
        clerk_authorized_parties=WEB,
        cors_origins=WEB,
    )
    assert ok.clerk_jwks_endpoint == f"{ISSUER}/.well-known/jwks.json"


# ---------------------------------------------------------------------------------------------
# API con Clerk: 401/403 y alta al primer uso
# ---------------------------------------------------------------------------------------------


def test_api_without_token_401(clerk_api: TestClient) -> None:
    r = clerk_api.get("/documents")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    # Las cabeceras del stub no sirven con Clerk.
    r = clerk_api.get(
        "/documents",
        headers={"X-User-Id": str(uuid.uuid4()), "X-Organization-Id": str(uuid.uuid4())},
    )
    assert r.status_code == 401


def test_api_expired_and_bad_issuer_401(clerk_api: TestClient) -> None:
    for token in (
        make_token(org=_org(), exp_in=-120),
        make_token(org=_org(), iss="https://otro.clerk.accounts.dev"),
    ):
        assert clerk_api.get("/documents", headers=_bearer(token)).status_code == 401


def test_api_without_org_403(clerk_api: TestClient) -> None:
    r = clerk_api.get("/documents", headers=_bearer(make_token()))
    assert r.status_code == 403
    assert "organización" in r.json()["detail"]
    r = clerk_api.post(
        "/documents",
        headers=_bearer(make_token()),
        files=[("files", ("f.pdf", b"%PDF-1.7\n%%EOF\n", "application/pdf"))],
    )
    assert r.status_code == 403


def test_first_use_provisions_org_and_user_once(
    clerk_api: TestClient, owner_engine: Engine
) -> None:
    org = _org()
    sub = f"user_{uuid.uuid4().hex[:10]}"
    token = make_token(sub=sub, org=org, email="ana@example.com", org_name="Pyme Prueba SAS")
    for _ in range(3):
        r = clerk_api.get("/documents", headers=_bearer(token))
        assert r.status_code == 200, r.text
        assert r.json() == []

    org_id = organization_uuid(org["id"])
    with Session(owner_engine) as s:
        org_row = s.get_one(Organization, org_id)
        assert org_row.external_auth_id == org["id"]
        assert org_row.name == "Pyme Prueba SAS"
        users = list(s.scalars(select(User).where(User.external_auth_id == sub)))
        assert len(users) == 1
        assert users[0].organization_id == org_id
        assert users[0].email == "ana@example.com"
        assert users[0].role == "admin"
        actions = list(
            s.scalars(select(AuditEvent.action).where(AuditEvent.organization_id == org_id))
        )
        assert sorted(actions) == ["organization.provisioned", "user.provisioned"]


def test_same_clerk_user_in_two_orgs(clerk_api: TestClient, owner_engine: Engine) -> None:
    sub = f"user_{uuid.uuid4().hex[:10]}"
    org1, org2 = _org(), _org()
    for org in (org1, org2):
        r = clerk_api.get("/documents", headers=_bearer(make_token(sub=sub, org=org)))
        assert r.status_code == 200, r.text
    with Session(owner_engine) as s:
        orgs = set(s.scalars(select(User.organization_id).where(User.external_auth_id == sub)))
        n = s.scalar(select(func.count()).select_from(User).where(User.external_auth_id == sub))
    assert orgs == {organization_uuid(org1["id"]), organization_uuid(org2["id"])}
    assert n == 2


def test_org_isolation_with_clerk(clerk_api: TestClient) -> None:
    org_a, org_b = _org(), _org()
    tok_a = make_token(sub="user_a_iso", org=org_a)
    tok_b = make_token(sub="user_b_iso", org=org_b)
    clerk_api.post(
        "/consent",
        headers=_bearer(tok_a),
        json={"version": clerk_api.get("/consent", headers=_bearer(tok_a)).json()["version"]},
    )
    r = clerk_api.post(
        "/documents",
        headers=_bearer(tok_a),
        files=[("files", ("a.pdf", b"%PDF-1.7\n%%EOF\n", "application/pdf"))],
    )
    assert r.status_code == 201, r.text
    doc_id = r.json()[0]["id"]
    assert clerk_api.get(f"/documents/{doc_id}", headers=_bearer(tok_b)).status_code == 404
    assert clerk_api.get("/documents", headers=_bearer(tok_b)).json() == []
    assert clerk_api.get(f"/documents/{doc_id}", headers=_bearer(tok_a)).status_code == 200
