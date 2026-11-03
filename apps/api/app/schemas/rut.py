"""RUT, formulario 001 de la DIAN (INSTRUCCIONES.md §6 y §8.2)."""

from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Literal

from pydantic import AfterValidator, BeforeValidator, Field

from app.schemas.base import EsquemaBase
from app.schemas.tipos import Dv, Nit


def _normalizar_codigo(valor: object) -> object:
    if isinstance(valor, int) and not isinstance(valor, bool):
        return f"{valor:02d}"
    if isinstance(valor, str):
        texto = valor.strip()
        return texto.zfill(2) if texto.isdigit() and len(texto) == 1 else texto
    return valor


def _formato(patron: str, descripcion: str) -> AfterValidator:
    regex = re.compile(patron)

    def verificar(valor: str) -> str:
        if not regex.match(valor):
            raise ValueError(descripcion)
        return valor

    return AfterValidator(verificar)


CodigoResponsabilidad = Annotated[
    str,
    BeforeValidator(_normalizar_codigo),
    _formato(r"^\d{2}$", "código de responsabilidad: dos dígitos, p. ej. '05'"),
]
"""Código de la casilla 53. No es Enum cerrado: ver ``app.schemas.catalogos``."""

CodigoCIIU = Annotated[
    str, _formato(r"^\d{4}$", "código CIIU: cuatro dígitos (CIIU Rev. 4 A.C.), p. ej. '4752'")
]


class RUT(EsquemaBase):
    tipo_documento: Literal["rut"] = "rut"
    nit: Nit | None = None
    dv: Dv | None = None
    tipo_contribuyente: Literal["persona_natural", "persona_juridica"] | None = None
    razon_social: str | None = Field(
        default=None, description="Persona jurídica: razón social. Natural: nombres y apellidos."
    )
    nombre_comercial: str | None = None
    municipio: str | None = None
    departamento: str | None = None
    direccion_seccional: str | None = None
    actividad_principal: CodigoCIIU | None = None
    actividades_secundarias: list[CodigoCIIU] = Field(default_factory=list)
    responsabilidades: list[CodigoResponsabilidad] = Field(
        default_factory=list, description="Códigos de la casilla 53 en el orden del formulario."
    )
    fecha_generacion: date | None = Field(
        default=None, description="Fecha de generación del documento (vigencia del catálogo)."
    )
