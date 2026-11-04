"""Tabla de precios configurable para calcular `llm_calls.cost_usd`.

Formato YAML (`app/llm/prices.yaml` o la ruta de `LLM_PRICES_PATH`)::

    version: 1
    precios:
      - proveedor: openai
        modelo: gpt-ejemplo
        usd_por_millon_entrada: "0.15"
        usd_por_millon_salida: "0.60"
        vigente_desde: 2026-11-01
        fuente: "página oficial de precios, consultada el …"

Un modelo sin precio no se puede llamar: sin precio no hay forma de respetar el tope por
documento (falla cerrado).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.llm.base import LLMNotConfiguredError, LLMUsage

DEFAULT_PRICES_PATH = Path(__file__).with_name("prices.yaml")
_MILLON = Decimal(1_000_000)
_SEIS_DECIMALES = Decimal("0.000001")


class ModelPrice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    proveedor: str
    modelo: str
    usd_por_millon_entrada: Decimal = Field(ge=0)
    usd_por_millon_salida: Decimal = Field(ge=0)
    vigente_desde: date | None = None
    vigente_hasta: date | None = None
    fuente: str | None = None

    def vigente_en(self, dia: date) -> bool:
        return (self.vigente_desde is None or self.vigente_desde <= dia) and (
            self.vigente_hasta is None or dia <= self.vigente_hasta
        )


class PriceTable(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = 1
    precios: list[ModelPrice] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path | None = None) -> PriceTable:
        data = yaml.safe_load((path or DEFAULT_PRICES_PATH).read_text(encoding="utf-8")) or {}
        return cls.model_validate(data)

    def price(self, provider: str, model: str, dia: date | None = None) -> ModelPrice:
        dia = dia or date.today()
        for p in self.precios:
            if p.proveedor == provider and p.modelo == model and p.vigente_en(dia):
                return p
        raise LLMNotConfiguredError(
            f"Sin precio vigente para {provider}/{model} en la tabla de precios "
            "(app/llm/prices.yaml o LLM_PRICES_PATH): no se llama al modelo."
        )

    def cost_usd(self, provider: str, model: str, usage: LLMUsage) -> Decimal:
        p = self.price(provider, model)
        cost = (
            Decimal(usage.input_tokens) * p.usd_por_millon_entrada
            + Decimal(usage.output_tokens) * p.usd_por_millon_salida
        ) / _MILLON
        return cost.quantize(_SEIS_DECIMALES)
