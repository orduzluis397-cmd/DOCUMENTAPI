"""Cuenta de cobro de una persona no obligada a facturar (INSTRUCCIONES.md §6 y §8.2)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field

from app.schemas.base import EsquemaBase
from app.schemas.tipos import Dv, MontoNoNegativo, Nit


class CuentaCobro(EsquemaBase):
    """Quien cobra suele ser persona natural: su NIT es su cédula (``dv`` puede no aparecer)."""

    tipo_documento: Literal["cuenta_cobro"] = "cuenta_cobro"
    numero: str | None = None
    fecha: date | None = Field(default=None, description="Fecha de expedición de la cuenta.")
    ciudad: str | None = None
    nombre_cobrador: str | None = None
    nit_cobrador: Nit | None = None
    dv_cobrador: Dv | None = None
    nombre_pagador: str | None = None
    nit_pagador: Nit | None = None
    dv_pagador: Dv | None = None
    concepto: str | None = None
    valor: MontoNoNegativo | None = Field(default=None, description="Valor total cobrado.")
    declara_no_responsable_iva: bool | None = Field(
        default=None,
        description="True si el texto declara que el cobrador no es responsable de IVA.",
    )
