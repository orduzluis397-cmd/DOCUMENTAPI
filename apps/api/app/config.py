"""Configuración de la API leída de variables de entorno (ver `.env.example`)."""

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valores por defecto = los de desarrollo local de `.env.example` e `infra/docker-compose.yml`.
# No son secretos reales; en cualquier entorno desplegado se sobreescriben por variables.
_LOCAL_DB = "postgresql+psycopg://contable_app:contable_app_local@127.0.0.1:5432/contable_ia"
_LOCAL_DB_MIGRATIONS = "postgresql+psycopg://contable:contable_local@127.0.0.1:5432/contable_ia"


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
    cors_origins: str = "http://localhost:3000"

    # PostgreSQL. La app usa SIEMPRE el rol sin BYPASSRLS (contable_app); el dueño del esquema
    # (contable) solo se usa en migraciones.
    database_url: str = _LOCAL_DB
    database_url_migrations: str = _LOCAL_DB_MIGRATIONS

    # Celery / Redis.
    celery_broker_url: str = "redis://127.0.0.1:6379/1"
    celery_result_backend: str = "redis://127.0.0.1:6379/2"
    # En pruebas: ejecuta las tareas en el mismo proceso, sin broker.
    celery_task_always_eager: bool = False

    # Almacenamiento de objetos (MinIO en local; R2/S3 en la nube).
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

    # ---- OCR / PDF.
    tesseract_cmd: str | None = None
    # Carpeta con los modelos de idioma (spa.traineddata). Si falta, Tesseract usa la suya.
    tessdata_prefix: str | None = None
    ocr_lang: str = "spa"
    ocr_dpi: int = Field(default=300, ge=72, le=600)
    ocr_max_pages: int = Field(default=10, gt=0)
    # Un PDF tiene capa de texto si trae al menos estos caracteres visibles por página.
    pdf_min_chars_per_page: int = Field(default=25, ge=1)

    @field_validator(
        "llm_model_extraction",
        "llm_model_classification",
        "anthropic_api_key",
        "openai_api_key",
        "vllm_base_url",
        "vllm_api_key",
        "llm_max_cost_per_doc_usd",
        "llm_prices_path",
        "tesseract_cmd",
        "tessdata_prefix",
        mode="before",
    )
    @classmethod
    def _empty_as_none(cls, value: Any) -> Any:
        # `.env.example` deja estas variables vacías: vacío significa "no configurado".
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Devuelve una única instancia de `Settings` por proceso."""
    return Settings()
