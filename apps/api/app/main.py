"""Punto de entrada de la API de Contable IA."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from app.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.app_version)


class HealthResponse(BaseModel):
    """Respuesta del chequeo de salud."""

    status: Literal["ok"]
    version: str
    env: str


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Chequeo de vida del servicio (no consulta dependencias externas)."""
    return HealthResponse(status="ok", version=settings.app_version, env=settings.app_env)
