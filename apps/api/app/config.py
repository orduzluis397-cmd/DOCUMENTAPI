"""Configuración de la API leída de variables de entorno (ver `.env.example`)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
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

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Devuelve una única instancia de `Settings` por proceso."""
    return Settings()
