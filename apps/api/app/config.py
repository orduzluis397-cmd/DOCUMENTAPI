"""Configuración de la API leída de variables de entorno (ver `.env.example`)."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


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


@lru_cache
def get_settings() -> Settings:
    """Devuelve una única instancia de `Settings` por proceso."""
    return Settings()
