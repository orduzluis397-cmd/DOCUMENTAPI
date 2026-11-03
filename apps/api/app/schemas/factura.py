"""Factura electrónica de venta (INSTRUCCIONES.md §8.2; verdad generada desde el XML UBL 2.1).

Definición de los montos (ver ``evals/datasets/GUIA.md``, sección Factura)
``[validar con contador asesor]``:

- ``subtotal`` = ``LegalMonetaryTotal/LineExtensionAmount`` (antes de impuestos).
- ``iva`` = suma de ``TaxTotal`` con esquema IVA (``01``).
- ``otros_impuestos`` = suma de los demás ``TaxTotal`` (INC, ICA, bolsas, ...).
- ``descuentos`` / ``cargos`` = ``AllowanceTotalAmount`` / ``ChargeTotalAmount``.
- ``anticipos`` = ``PrepaidAmount``.
- ``retenciones`` = suma de ``WithholdingTaxTotal`` (ReteFuente, ReteIVA, ReteICA).
- ``total`` = ``PayableAmount`` = **valor facturado**: las retenciones **no** se restan.
- ``neto_a_pagar`` (derivado, no se anota) = ``total - retenciones``: lo que suele verse en el
  extracto bancario.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.schemas.base import EsquemaBase
from app.schemas.tipos import Cantidad, Cufe, Dv, MontoNoNegativo, Nit


class LineaFactura(EsquemaBase):
    """Una línea (``InvoiceLine``) de la factura."""

    descripcion: str | None = None
    cantidad: Cantidad | None = None
    valor_unitario: Cantidad | None = Field(
        default=None, description="Precio unitario sin IVA (PriceAmount)."
    )
    valor_total: MontoNoNegativo | None = Field(
        default=None, description="Valor de la línea sin IVA (LineExtensionAmount de la línea)."
    )
    tarifa_iva: Cantidad | None = Field(
        default=None, ge=0, le=100, description="Porcentaje de IVA (19, 5, 0)."
    )
    iva: MontoNoNegativo | None = None


class Factura(EsquemaBase):
    """Campos de §8.2 más los componentes del total en UBL."""

    tipo_documento: Literal["factura"] = "factura"
    numero: str | None = Field(
        default=None, description="Prefijo + consecutivo, p. ej. SETP990000001."
    )
    cufe: Cufe | None = None
    fecha_emision: date | None = None
    nit_emisor: Nit | None = None
    dv_emisor: Dv | None = None
    razon_social_emisor: str | None = None
    nit_adquirente: Nit | None = None
    dv_adquirente: Dv | None = None
    razon_social_adquirente: str | None = None
    subtotal: MontoNoNegativo | None = None
    descuentos: MontoNoNegativo | None = None
    cargos: MontoNoNegativo | None = None
    iva: MontoNoNegativo | None = None
    otros_impuestos: MontoNoNegativo | None = None
    anticipos: MontoNoNegativo | None = None
    retenciones: MontoNoNegativo | None = None
    total: MontoNoNegativo | None = Field(
        default=None, description="PayableAmount: valor facturado, sin restar retenciones."
    )
    lineas: list[LineaFactura] = Field(default_factory=list)

    @property
    def neto_a_pagar(self) -> Decimal | None:
        """``total - retenciones`` (derivado; no se anota ni se serializa)."""
        if self.total is None:
            return None
        return self.total - (self.retenciones or Decimal("0"))
