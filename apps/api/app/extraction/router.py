"""Enrutador de extracción en cascada (F0-09, #19; INSTRUCCIONES.md §8.3).

1. ZIP / XML de factura electrónica → parser determinista con lxml, **sin LLM** (regla dura 7).
2. PDF con capa de texto → texto con pypdfium2.
3. Imagen o PDF escaneado → OCR con Tesseract `spa`.
4. Texto de 2 o 3 → clasificación con LLM (`Literal` de los 5 tipos) → extracción con Instructor
   al esquema del tipo → validadores de dominio → reintentos acotados → `is_doubtful`.

El tipo de archivo se decide por la firma de los bytes, no por el nombre ni el `Content-Type`.
Los clientes de LLM y OCR se construyen solo si la ruta los necesita (la ruta XML no los toca).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic_core import to_jsonable_python

from app.extraction import llm_extract
from app.extraction.fields import failed_fields, to_field_values
from app.extraction.ocr import OcrEngine, ocr_image, ocr_pdf
from app.extraction.pdf_text import extract_text
from app.extraction.types import ExtractionError, ExtractionOutcome, Method
from app.extraction.xml_ubl import is_zip, parse_ubl
from app.files import sniff
from app.llm.base import LLMError, LLMNotConfiguredError
from app.observability.llm_calls import CostCapExceededError, TrackedLLM
from app.observability.tracing import get_tracer
from app.schemas.validators import ResultadoValidacion, validar_factura

_UBL_NOTE = {
    "nota_credito": "Nota crédito",
    "nota_debito": "Nota débito",
}


@dataclass(frozen=True)
class RouterConfig:
    model_extraction: str | None
    model_classification: str | None = None
    max_retries: int = 2
    max_input_chars: int = 40_000
    pdf_min_chars_per_page: int = 25
    ocr_dpi: int = 300
    ocr_max_pages: int = 10


def _validaciones_json(vals: list[ResultadoValidacion]) -> list[dict[str, Any]]:
    return [v.model_dump(mode="json") for v in vals]


def extract_document(
    data: bytes,
    *,
    config: RouterConfig,
    llm_factory: Callable[[], TrackedLLM],
    ocr_factory: Callable[[], OcrEngine],
    trace_id: str,
    hoy: date | None = None,
) -> ExtractionOutcome:
    """Extrae un documento. Nunca lanza por errores esperados: los refleja en el resultado."""
    tracer = get_tracer()
    kind = "application/zip" if is_zip(data) else sniff(data)
    with tracer.span("documento", trace_id, content_type=kind):
        if kind in ("application/zip", "application/xml"):
            return _from_xml(data, trace_id, hoy)
        if kind == "application/pdf":
            method: Method = "pdf_text"
            try:
                with tracer.span("pdf_texto", trace_id):
                    pdf = extract_text(data)
                if pdf.has_text_layer(config.pdf_min_chars_per_page):
                    pages = pdf.pages
                else:
                    method = "ocr"
                    with tracer.span("ocr", trace_id, origen="pdf"):
                        pages = ocr_pdf(data, ocr_factory(), config.ocr_dpi, config.ocr_max_pages)
            except ExtractionError as exc:
                return ExtractionOutcome(status="failed", method=method, error=str(exc))
        elif kind in ("image/png", "image/jpeg", "image/tiff"):
            method = "ocr"
            try:
                with tracer.span("ocr", trace_id, origen="imagen"):
                    pages = ocr_image(data, ocr_factory())
            except ExtractionError as exc:
                return ExtractionOutcome(status="failed", method=method, error=str(exc))
        else:
            return ExtractionOutcome(
                status="failed", method="pdf_text", error="Tipo de archivo no soportado"
            )
        return _from_text(pages, method, config, llm_factory, hoy)


# ------------------------------------------------------------------------------ XML


def _from_xml(data: bytes, trace_id: str, hoy: date | None) -> ExtractionOutcome:
    with get_tracer().span("xml", trace_id):
        try:
            ubl = parse_ubl(data)
        except ExtractionError as exc:
            return ExtractionOutcome(status="failed", method="xml_parser", error=str(exc))
    with get_tracer().span("validar", trace_id, doc_type=ubl.kind):
        validaciones = validar_factura(ubl.factura, hoy)
        doubtful = failed_fields(validaciones) | set(ubl.invalid)
    error = None
    if ubl.kind in _UBL_NOTE:
        error = (
            f"{_UBL_NOTE[ubl.kind]} leída con el esquema de factura: su esquema propio está "
            "pendiente (GUIA.md §9); requiere revisión."
        )
    elif doubtful:
        error = "Campos del XML que no pasan los validadores: " + ", ".join(sorted(doubtful))
    return ExtractionOutcome(
        status="needs_review" if error else "extracted",
        method="xml_parser",
        doc_type=ubl.kind,
        fields=to_field_values(ubl.factura, doubtful),
        error=error,
        raw_output={
            "ruta": "xml",
            "ubl": ubl.kind,
            "validaciones": _validaciones_json(validaciones),
            "invalidos": to_jsonable_python(ubl.invalid),
        },
    )


# ------------------------------------------------------------------------------ texto + LLM


def _from_text(
    pages: list[str],
    method: Method,
    config: RouterConfig,
    llm_factory: Callable[[], TrackedLLM],
    hoy: date | None,
) -> ExtractionOutcome:
    text = "\n\n".join(f"--- página {i} ---\n{p}" for i, p in enumerate(pages, 1) if p.strip())
    if not text.strip():
        return ExtractionOutcome(
            status="needs_review", method=method, error="El documento no tiene texto legible."
        )
    truncated = len(text) > config.max_input_chars
    text = text[: config.max_input_chars]
    raw: dict[str, Any] = {"ruta": method, "paginas": len(pages), "caracteres": len(text)}
    if truncated:
        raw["texto_truncado"] = True

    model = config.model_extraction
    try:
        if not model:
            raise LLMNotConfiguredError("Falta LLM_MODEL_EXTRACTION.")
        llm = llm_factory()
    except LLMNotConfiguredError as exc:
        return ExtractionOutcome(
            status="failed", method=method, error=f"LLM no configurado: {exc}", raw_output=raw
        )

    outcome = ExtractionOutcome(status="failed", method=method, model=model, raw_output=raw)
    try:
        doc_type = llm_extract.classify(
            text,
            llm,
            model=config.model_classification or model,
            max_retries=config.max_retries,
        )
        outcome.doc_type = doc_type
        result = llm_extract.extract(
            text, doc_type, llm, model=model, max_retries=config.max_retries, hoy=hoy
        )
    except CostCapExceededError as exc:
        outcome.status = "needs_review"
        outcome.error = str(exc)
        raw["costo_usd"] = str(llm.spent_usd)
        return outcome
    except ExtractionError as exc:
        outcome.status = "needs_review"
        outcome.error = str(exc)
        return outcome
    except LLMNotConfiguredError as exc:
        outcome.error = f"LLM no configurado: {exc}"
        return outcome
    except LLMError as exc:
        outcome.error = f"Error del proveedor LLM: {exc}"
        return outcome

    outcome.prompt_version = result.prompt_version
    raw.update(
        intentos=result.attempts,
        llamadas=llm.calls,
        costo_usd=str(llm.spent_usd),
        validaciones=_validaciones_json(result.validaciones),
        invalidos=to_jsonable_python(result.invalid),
    )
    problems: list[str] = []
    if result.cap_exceeded:
        raw["tope_costo_superado"] = True
        problems.append(
            f"Tope de costo por documento superado (US${llm.spent_usd} de US${llm.max_cost_usd}); "
            "se detuvo la extracción."
        )
    if result.documento is None:
        problems.append("La salida del LLM no se pudo llevar al esquema.")
        outcome.status = "needs_review"
        outcome.error = " ".join(problems)
        return outcome
    outcome.fields = to_field_values(result.documento, result.doubtful)
    if result.doubtful:
        problems.append("Campos dudosos tras reintentos: " + ", ".join(sorted(result.doubtful)))
    outcome.status = "needs_review" if problems else "extracted"
    outcome.error = " ".join(problems) or None
    return outcome
