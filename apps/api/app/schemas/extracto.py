"""Extracto bancario (INSTRUCCIONES.md §8.2; conciliación en la fase 3)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field

from app.schemas.base import EsquemaBase
from app.schemas.tipos import Monto, MontoNoNegativo, Nit


class Movimiento(EsquemaBase):
    """Un movimiento. ``valor`` con signo: positivo = crédito (entra), negativo = débito (sale)."""

    fecha: date | None = None
    descripcion: str | None = None
    referencia: str | None = None
    valor: Monto | None = None
    saldo: Monto | None = Field(default=None, description="Saldo tras el movimiento, si aparece.")


class ExtractoBancario(EsquemaBase):
    tipo_documento: Literal["extracto"] = "extracto"
    banco: str | None = None
    numero_cuenta: str | None = Field(
        default=None, description="Tal como aparece (suele venir enmascarado)."
    )
    tipo_cuenta: Literal["ahorros", "corriente"] | None = None
    titular: str | None = None
    nit_titular: Nit | None = None
    periodo_inicio: date | None = None
    periodo_fin: date | None = None
    saldo_inicial: Monto | None = None
    saldo_final: Monto | None = None
    total_creditos: MontoNoNegativo | None = None
    total_debitos: MontoNoNegativo | None = Field(
        default=None, description="Suma de débitos en valor absoluto, si el extracto la trae."
    )
    movimientos: list[Movimiento] = Field(default_factory=list)
