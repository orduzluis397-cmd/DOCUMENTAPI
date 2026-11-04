"""Tipos del enrutador de extracción."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, get_args

from app.schemas import RUT, Contrato, CuentaCobro, ExtractoBancario, Factura

DocType = Literal["factura", "cuenta_cobro", "rut", "extracto", "contrato"]
DOC_TYPES: tuple[str, ...] = get_args(DocType)

Documento = Factura | CuentaCobro | RUT | ExtractoBancario | Contrato

SCHEMAS: dict[str, type[Documento]] = {
    "factura": Factura,
    "cuenta_cobro": CuentaCobro,
    "rut": RUT,
    "extracto": ExtractoBancario,
    "contrato": Contrato,
}

# Versión de los esquemas y de la guía de anotación (evals/datasets/GUIA.md).
SCHEMA_VERSION = "guia-0.1"

Method = Literal["xml_parser", "pdf_text", "ocr", "llm"]
OutcomeStatus = Literal["extracted", "needs_review", "failed"]


class ExtractionError(Exception):
    """Error esperado de una ruta (archivo ilegible, tipo no soportado, OCR no disponible…)."""


@dataclass(frozen=True, slots=True)
class FieldValue:
    name: str  # ruta del campo: "nit_emisor", "lineas[0].cantidad"
    value: Any  # valor JSON (montos como texto decimal, fechas ISO)
    is_doubtful: bool = False


@dataclass
class ExtractionOutcome:
    """Lo que el worker persiste en `extractions`/`extracted_fields` y el estado del documento."""

    status: OutcomeStatus
    method: Method
    doc_type: str | None = None
    fields: list[FieldValue] = field(default_factory=list)
    model: str | None = None
    prompt_version: str | None = None
    schema_version: str | None = SCHEMA_VERSION
    error: str | None = None
    raw_output: dict[str, Any] = field(default_factory=dict)

    @property
    def doubtful_fields(self) -> list[str]:
        return [f.name for f in self.fields if f.is_doubtful]
