"""Contrato de prestación de servicios (INSTRUCCIONES.md §8.2)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field

from app.schemas.base import EsquemaBase
from app.schemas.tipos import Dv, MontoNoNegativo, Nit


class ParteContrato(EsquemaBase):
    rol: Literal["contratante", "contratista"] | None = None
    nombre: str | None = None
    nit: Nit | None = None
    dv: Dv | None = None
    representante_legal: str | None = None


class Contrato(EsquemaBase):
    tipo_documento: Literal["contrato"] = "contrato"
    partes: list[ParteContrato] = Field(default_factory=list)
    objeto: str | None = None
    valor: MontoNoNegativo | None = Field(
        default=None, description="Valor total del contrato; null si es indeterminado."
    )
    forma_pago: str | None = None
    fecha_firma: date | None = None
    fecha_inicio: date | None = Field(default=None, description="Inicio de la vigencia.")
    fecha_fin: date | None = Field(default=None, description="Fin de la vigencia.")
    duracion: str | None = Field(
        default=None, description="Duración tal como aparece si no hay fecha_fin, p. ej. '6 meses'."
    )
