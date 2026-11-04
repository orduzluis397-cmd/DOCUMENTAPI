"""Configuración de la API leída de variables de entorno (ver `.env.example`)."""

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valores por defecto = los de desarrollo local de `.env.example` e `infra/docker-compose.yml`.
# No son secretos reales; en cualquier entorno desplegado se sobreescriben por variables.
_LOCAL_DB = "postgresql+psycopg://contable_app:contable_app_local@127.0.0.1:5432/contable_ia"
_LOCAL_DB_MIGRATIONS = "postgresql+psycopg://contable:contable_local@127.0.0.1:5432/contable_ia"
# Copia del texto de la autorización de datos (docs/legal) en el repositorio; en la imagen de
# Docker se copia a /app/legal y se apunta con CONSENT_DOCUMENT_PATH.
_REPO_CONSENT = Path(__file__).resolve().parents[3] / "docs/legal/autorizacion-uso-documentos.md"

# Entornos donde se admite el stub de autenticación por cabeceras (app/auth.py).
STUB_AUTH_ENVS = frozenset({"local", "test"})


class Settings(BaseSettings):
    """Ajustes de la aplicación. Ningún valor por defecto es un secreto real."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Contable IA API"
    app_env: Literal["local", "test", "staging", "production"] = "local"
    app_version: str = "0.1.0"
    # Orígenes permitidos (separados por coma). En la demo: SOLO el dominio de Vercel.
    cors_origins: str = "http://localhost:3000"

    # ---- Autenticación. `stub` (cabeceras X-User-Id/X-Organization-Id) solo en local/test;
    # en staging/production es obligatorio `clerk` (se valida al arrancar).
    auth_provider: Literal["stub", "clerk"] = "stub"
    # Emisor de los JWT de Clerk = Frontend API URL (https://<app>.clerk.accounts.dev o el
    # dominio propio). Los JWKS se leen de <issuer>/.well-known/jwks.json salvo CLERK_JWKS_URL.
    clerk_issuer: str | None = None
    clerk_jwks_url: str | None = None
    # Valores aceptados en el claim `azp` (origen de la web), separados por coma. Obligatorio
    # fuera de local/test.
    clerk_authorized_parties: str = ""
    # Audiencia esperada (`aud`), solo si se configuró en una plantilla de JWT de Clerk.
    clerk_audience: str | None = None
    clerk_jwks_cache_s: int = Field(default=3600, ge=60)
    clerk_leeway_s: int = Field(default=5, ge=0, le=60)

    # ---- Autorización de uso de datos (Ley 1581): texto y etiqueta de versión.
    consent_document_path: Path = _REPO_CONSENT
    consent_version_label: str = "borrador-2026-11-04"

    # PostgreSQL. La app usa SIEMPRE el rol sin BYPASSRLS (contable_app); el dueño del esquema
    # (contable) solo se usa en migraciones.
    database_url: str = _LOCAL_DB
    database_url_migrations: str = _LOCAL_DB_MIGRATIONS

    # Celery / Redis.
    celery_broker_url: str = "redis://127.0.0.1:6379/1"
    celery_result_backend: str = "redis://127.0.0.1:6379/2"
    # En pruebas: ejecuta las tareas en el mismo proceso, sin broker.
    celery_task_always_eager: bool = False
    # Segundos que el worker espera en cada BRPOP antes de volver a preguntar. En Upstash (cuota
    # de comandos) conviene 30: la tarea igual llega al instante; solo baja el sondeo en vacío.
    celery_broker_polling_interval_s: float | None = Field(default=None, gt=0, le=300)

    # Almacenamiento de objetos (MinIO en local; Supabase Storage vía su endpoint S3 en la demo).
    s3_endpoint_url: str | None = "http://127.0.0.1:9000"
    s3_region: str = "us-east-1"
    s3_bucket: str = "contable-ia-documents"
    s3_access_key_id: str = "minioadmin"
    s3_secret_access_key: str = "minioadmin_local"  # noqa: S105 - credencial local de MinIO

    # Carga de documentos.
    upload_max_bytes: int = Field(default=20 * 1024 * 1024, gt=0)
    upload_max_files: int = Field(default=20, gt=0)

    # ---- LLM (F0-10). La temperatura NO es configurable: va fija en 0 en app/llm/base.py.
    llm_provider: Literal["anthropic", "openai", "vllm"] = "anthropic"
    llm_model_extraction: str | None = None
    # Modelo de clasificación; si falta, se usa el de extracción.
    llm_model_classification: str | None = None
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    vllm_base_url: str | None = None
    vllm_api_key: SecretStr | None = None
    llm_timeout_s: float = Field(default=60.0, gt=0)
    llm_max_output_tokens: int = Field(default=4096, gt=0)
    # Reintentos acotados tras el primer intento (esquema o validadores de dominio).
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    # Tope de costo por documento (USD). Sin tope configurado NO se llama al LLM (falla cerrado).
    llm_max_cost_per_doc_usd: Decimal | None = Field(default=None, gt=0)
    # Tabla de precios (YAML). Por defecto, app/llm/prices.yaml.
    llm_prices_path: Path | None = None
    # Máximo de caracteres de texto que se envían al LLM (acota el costo).
    llm_max_input_chars: int = Field(default=40_000, gt=0)
    # Presupuesto global (todas las organizaciones) contra la suma de llm_calls. Si falta alguno,
    # NO se llama al LLM (falla cerrado). Día y mes en hora de Colombia (UTC-5).
    llm_daily_budget_usd: Decimal | None = Field(default=None, gt=0)
    llm_monthly_budget_usd: Decimal | None = Field(default=None, gt=0)
    # Con false (por defecto) no sale ninguna llamada a un proveedor externo (anthropic,
    # openai); solo se admite vLLM en la máquina o la red local. La política final la decide
    # el usuario (regla dura 1: ningún documento sin anonimizar va a una API externa).
    llm_external_enabled: bool = False

    # ---- Worker.
    # Un documento en `processing` sin terminar tras este tiempo se puede reclamar de nuevo
    # (reentrega de Celery tras una caída). Debe superar el peor tiempo de procesamiento.
    processing_lease_s: int = Field(default=900, ge=60)

    # ---- OCR / PDF.
    tesseract_cmd: str | None = None
    # Carpeta con los modelos de idioma (spa.traineddata). Si falta, Tesseract usa la suya.
    tessdata_prefix: str | None = None
    ocr_lang: str = "spa"
    ocr_dpi: int = Field(default=300, ge=72, le=600)
    # Páginas (o cuadros de un TIFF) máximas con OCR por documento; el resto se omite.
    ocr_max_pages: int = Field(default=10, gt=0)
    # Tope de píxeles por página antes del OCR (se baja la escala si hace falta).
    ocr_max_pixels: int = Field(default=25_000_000, ge=1_000_000)
    ocr_timeout_s: int = Field(default=60, gt=0)
    # Una página de PDF tiene capa de texto si trae al menos estos caracteres visibles.
    pdf_min_chars_per_page: int = Field(default=25, ge=1)

    @field_validator(
        "llm_model_extraction",
        "llm_model_classification",
        "anthropic_api_key",
        "openai_api_key",
        "vllm_base_url",
        "vllm_api_key",
        "llm_max_cost_per_doc_usd",
        "llm_daily_budget_usd",
        "llm_monthly_budget_usd",
        "llm_prices_path",
        "tesseract_cmd",
        "tessdata_prefix",
        "clerk_issuer",
        "clerk_jwks_url",
        "clerk_audience",
        "celery_broker_polling_interval_s",
        mode="before",
    )
    @classmethod
    def _empty_as_none(cls, value: Any) -> Any:
        # `.env.example` deja estas variables vacías: vacío significa "no configurado".
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _deployed_requires_real_auth(self) -> "Settings":
        # Falla al arrancar en vez de quedar abierta: fuera de local/test no hay stub.
        if self.app_env in STUB_AUTH_ENVS:
            return self
        if self.auth_provider != "clerk":
            raise ValueError(f"APP_ENV={self.app_env} exige AUTH_PROVIDER=clerk")
        if not self.clerk_issuer or not self.clerk_issuer.startswith("https://"):
            raise ValueError("CLERK_ISSUER (https://...) es obligatorio fuera de local/test")
        if not self.clerk_authorized_party_list:
            raise ValueError("CLERK_AUTHORIZED_PARTIES es obligatorio fuera de local/test")
        if any(o == "*" for o in self.cors_origin_list):
            raise ValueError("CORS_ORIGINS no puede ser '*' fuera de local/test")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @property
    def clerk_authorized_party_list(self) -> list[str]:
        return [
            o.strip().rstrip("/") for o in self.clerk_authorized_parties.split(",") if o.strip()
        ]

    @property
    def clerk_jwks_endpoint(self) -> str | None:
        if self.clerk_jwks_url:
            return self.clerk_jwks_url
        if self.clerk_issuer:
            return self.clerk_issuer.rstrip("/") + "/.well-known/jwks.json"
        return None


@lru_cache
def get_settings() -> Settings:
    """Devuelve una única instancia de `Settings` por proceso."""
    return Settings()
