"""Punto de entrada de la API de Contable IA."""

from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import get_settings
from app.routers import consent, documents, fields

settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.app_version)


def _allowed_headers() -> list[str]:
    headers = ["Content-Type", "Authorization"]
    if settings.auth_provider == "stub":
        # Stub de autenticación local (app/auth.py).
        headers += ["X-User-Id", "X-Organization-Id"]
    return headers


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    # Sin cookies: la web manda el token en Authorization (Bearer).
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=_allowed_headers(),
    max_age=600,
)

app.include_router(consent.router)
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
