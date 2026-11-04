"""Esquemas Pydantic v2 de los documentos (INSTRUCCIONES.md §8.2) y su unión discriminada."""

from typing import Annotated

from pydantic import Field, TypeAdapter

from app.schemas.contrato import Contrato, ParteContrato
from app.schemas.cuenta_cobro import CuentaCobro
from app.schemas.extracto import ExtractoBancario, Movimiento
from app.schemas.factura import Factura, LineaFactura
from app.schemas.rut import RUT

Documento = Annotated[
    Factura | CuentaCobro | RUT | ExtractoBancario | Contrato,
    Field(discriminator="tipo_documento"),
]
"""Cualquier documento; ``tipo_documento`` decide el esquema (JSON del conjunto dorado)."""

documento_adapter: TypeAdapter[Factura | CuentaCobro | RUT | ExtractoBancario | Contrato] = (
    TypeAdapter(Documento)
)

__all__ = [
    "RUT",
    "Contrato",
    "CuentaCobro",
    "Documento",
    "ExtractoBancario",
    "Factura",
    "LineaFactura",
    "Movimiento",
    "ParteContrato",
    "documento_adapter",
]
