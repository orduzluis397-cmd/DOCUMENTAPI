"""Punto de entrada de la API de Contable IA."""

from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import get_settings
from app.routers import documents, fields

settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.app_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    # X-User-Id / X-Organization-Id: stub de autenticación local (app/auth.py).
    allow_headers=["Content-Type", "Authorization", "X-User-Id", "X-Organization-Id"],
)

app.include_router(documents.router)
app.include_router(fields.router)


class HealthResponse(BaseModel):
    """Respuesta del chequeo de salud."""

    status: Literal["ok"]
    version: str
    env: str


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Chequeo de vida del servicio (no consulta dependencias externas)."""
    return HealthResponse(status="ok", version=settings.app_version, env=settings.app_env)
