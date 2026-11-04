"""Fixtures de pruebas contra el Postgres de docker compose (base `contable_ia_test`).

- Migraciones con el rol dueño (`DATABASE_URL_TEST_MIGRATIONS`).
- La API y las pruebas de RLS usan el rol de la app (`DATABASE_URL_TEST`, `contable_app`).
- Si la base no responde, las pruebas de BD se OMITEN en local y FALLAN si `REQUIRE_DB=1` (CI).
"""

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

_TEST_DB = "contable_ia_test"
DB_URL = os.environ.get(
    "DATABASE_URL_TEST",
    f"postgresql+psycopg://contable_app:contable_app_local@127.0.0.1:5432/{_TEST_DB}",
)
DB_URL_MIGRATIONS = os.environ.get(
    "DATABASE_URL_TEST_MIGRATIONS",
    f"postgresql+psycopg://contable:contable_local@127.0.0.1:5432/{_TEST_DB}",
)

# Antes de importar la app: entorno de prueba y la base de pruebas (nunca la de desarrollo).
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = DB_URL
os.environ["DATABASE_URL_MIGRATIONS"] = DB_URL_MIGRATIONS
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"

from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from alembic import command  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.consent import load_consent_document  # noqa: E402
from app.db.models import (  # noqa: E402
    AuditEvent,
    DataUseConsent,
    Document,
    ExtractedField,
    Extraction,
    LlmCall,
    Organization,
    User,
)
from app.deps import get_enqueue  # noqa: E402
from app.main import app  # noqa: E402
from app.storage import get_storage  # noqa: E402

API_DIR = Path(__file__).resolve().parents[1]


def alembic_config() -> Config:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.attributes["sqlalchemy.url"] = DB_URL_MIGRATIONS
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def owner_engine() -> Iterator[Engine]:
    engine = create_engine(DB_URL_MIGRATIONS, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        engine.dispose()
        msg = f"Postgres de pruebas no disponible ({_TEST_DB}): {exc.__class__.__name__}"
        if os.environ.get("REQUIRE_DB") == "1":
            pytest.fail(msg)
        pytest.skip(msg + " — levanta `docker compose -f infra/docker-compose.yml up -d`")
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def migrated(owner_engine: Engine) -> None:
    """Base limpia: baja todo y aplica las migraciones hasta head."""
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def app_engine(migrated: None) -> Iterator[Engine]:
    engine = create_engine(DB_URL, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def app_factory(app_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=app_engine, expire_on_commit=False)


@dataclass
class Tenant:
    org_id: uuid.UUID
    user_id: uuid.UUID
    document_id: uuid.UUID
    extraction_id: uuid.UUID
    field_id: uuid.UUID
    doubtful_field_id: uuid.UUID

    @property
    def headers(self) -> dict[str, str]:
        return {"X-User-Id": str(self.user_id), "X-Organization-Id": str(self.org_id)}


def current_consent_sha() -> str:
    s = get_settings()
    return load_consent_document(s.consent_document_path, s.consent_version_label).sha256


def create_tenant(owner_engine: Engine, name: str, *, consent: bool = True) -> Tenant:
    """Crea una organización completa con el rol dueño (superusuario: ignora RLS).

    Con `consent=True` el usuario ya aceptó la autorización de uso de datos vigente.
    """
    org_id, user_id, doc_id, ext_id = (uuid.uuid4() for _ in range(4))
    field_id, doubtful_id = uuid.uuid4(), uuid.uuid4()
    with Session(owner_engine) as s:
        s.add(Organization(id=org_id, name=name))
        s.flush()
        s.add(User(id=user_id, organization_id=org_id, email=f"{org_id}@test.local"))
        s.flush()
        if consent:
            s.add(
                DataUseConsent(
                    organization_id=org_id,
                    user_id=user_id,
                    version="test",
                    text_sha256=current_consent_sha(),
                )
            )
        s.add(
            Document(
                id=doc_id,
                organization_id=org_id,
                uploaded_by=user_id,
                filename=f"{name}.pdf",
                content_type="application/pdf",
                size_bytes=10,
                sha256="0" * 64,
                storage_key=f"org/{org_id}/documents/{doc_id}.pdf",
                status="needs_review",
            )
        )
        s.flush()
        s.add(
            Extraction(
                id=ext_id,
                organization_id=org_id,
                document_id=doc_id,
                method="llm",
                model="modelo-x",
                prompt_version="v1",
                trace_id="trace-" + name,
            )
        )
        s.flush()
        s.add_all(
            [
                ExtractedField(
                    id=field_id,
                    organization_id=org_id,
                    extraction_id=ext_id,
                    name="factura.numero",
                    value=f"{name}-001",
                ),
                ExtractedField(
                    id=doubtful_id,
                    organization_id=org_id,
                    extraction_id=ext_id,
                    name="totales.total",
                    value=1000,
                    is_doubtful=True,
                    confidence=0.4,
                ),
                LlmCall(
                    organization_id=org_id,
                    document_id=doc_id,
                    provider="anthropic",
                    model="modelo-x",
                    input_tokens=100,
                    output_tokens=20,
                    latency_ms=500,
                ),
                AuditEvent(
                    organization_id=org_id,
                    actor="system:test",
                    action="seed",
                    entity="documents",
                    entity_id=str(doc_id),
                ),
            ]
        )
        s.commit()
    return Tenant(org_id, user_id, doc_id, ext_id, field_id, doubtful_id)


@pytest.fixture
def tenant_a(owner_engine: Engine, migrated: None) -> Tenant:
    return create_tenant(owner_engine, "org-a")


@pytest.fixture
def tenant_b(owner_engine: Engine, migrated: None) -> Tenant:
    return create_tenant(owner_engine, "org-b")


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    def get(self, key: str) -> bytes:
        return self.objects[key][0]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


@dataclass
class ApiHarness:
    client: TestClient
    storage: FakeStorage
    enqueued: list[tuple[uuid.UUID, uuid.UUID]]


@pytest.fixture
def api(migrated: None) -> Iterator[ApiHarness]:
    storage = FakeStorage()
    enqueued: list[tuple[uuid.UUID, uuid.UUID]] = []

    def fake_enqueue(document_id: uuid.UUID, organization_id: uuid.UUID) -> None:
        enqueued.append((document_id, organization_id))

    def enqueue_dep() -> Any:
        return fake_enqueue

    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_enqueue] = enqueue_dep
    with TestClient(app, raise_server_exceptions=False) as client:
        yield ApiHarness(client, storage, enqueued)
    app.dependency_overrides.clear()
