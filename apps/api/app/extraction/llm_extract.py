"""Clasificación y extracción con LLM (Instructor), con reintentos acotados y campos dudosos.

Cada intento es una llamada registrada en `llm_calls` (vía `TrackedLLM`). Un intento falla si
la salida no pasa el esquema Pydantic o si no pasa los validadores de dominio
(`app.schemas.validators`); el siguiente intento recibe los errores. Tras agotar los reintentos
se queda el mejor intento y sus campos que siguen sin validar quedan con `is_doubtful=true`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.extraction.fields import failed_fields, salvage
from app.extraction.prompts import load_prompt
from app.extraction.types import SCHEMAS, DocType, Documento, ExtractionError
from app.llm.base import Message
from app.observability.llm_calls import CostCapExceededError, TrackedLLM
from app.observability.tracing import get_tracer
from app.schemas.validators import ResultadoValidacion, validar_documento


class Clasificacion(BaseModel):
    """Salida de la clasificación: uno de los 5 tipos."""

    model_config = ConfigDict(extra="forbid")

    tipo_documento: DocType


@dataclass
class LlmExtraction:
    doc_type: DocType
    documento: Documento | None
    doubtful: set[str] = field(default_factory=set)
    invalid: dict[str, Any] = field(default_factory=dict)
    validaciones: list[ResultadoValidacion] = field(default_factory=list)
    attempts: int = 0
    cap_exceeded: bool = False
    prompt_version: str = ""


def classify(text: str, llm: TrackedLLM, *, model: str, max_retries: int) -> DocType:
    prompt = load_prompt("clasificacion")
    messages = [
        Message("system", prompt.system),
        Message("user", prompt.render_user(texto=text)),
    ]
    last_error = ""
    for attempt in range(1 + max_retries):
        with get_tracer().span(
            "clasificar" if attempt == 0 else "reintentar", llm.trace_id, intento=attempt + 1
        ):
            result = llm.structured(
                purpose="clasificacion",
                prompt_version=prompt.version,
                model=model,
                messages=messages,
                response_model=Clasificacion,
            )
        if result.value is not None:
            return result.value.tipo_documento
        last_error = result.validation_error or "salida vacía"
    raise ExtractionError(f"No se pudo clasificar el documento: {last_error[:300]}")


def _feedback(validaciones: list[ResultadoValidacion], invalid: dict[str, Any]) -> str:
    lines = [
        f"- {v.regla} ({', '.join(v.campos)}): {v.mensaje}"
        for v in validaciones
        if not v.ok and v.severidad == "error"
    ]
    lines += [
        f"- {campo}: valor {valor!r} no cumple el esquema" for campo, valor in invalid.items()
    ]
    return "\n".join(lines)


def extract(
    text: str,
    doc_type: DocType,
    llm: TrackedLLM,
    *,
    model: str,
    max_retries: int,
    hoy: date | None = None,
) -> LlmExtraction:
    prompt = load_prompt("extraccion")
    schema = SCHEMAS[doc_type]
    base = [
        Message("system", prompt.system),
        Message(
            "user",
            prompt.render_user(
                tipo=doc_type, instrucciones=prompt.tipos.get(doc_type, ""), texto=text
            ),
        ),
    ]
    messages = list(base)
    out = LlmExtraction(doc_type=doc_type, documento=None, prompt_version=prompt.version)
    best_score: int | None = None
    tracer = get_tracer()

    for attempt in range(1 + max_retries):
        try:
            with tracer.span(
                "extraer" if attempt == 0 else "reintentar",
                llm.trace_id,
                doc_type=doc_type,
                intento=attempt + 1,
            ):
                result = llm.structured(
                    purpose="extraccion",
                    prompt_version=prompt.version,
                    model=model,
                    messages=messages,
                    response_model=schema,
                )
        except CostCapExceededError:
            out.cap_exceeded = True
            break
        out.attempts += 1

        with tracer.span("validar", llm.trace_id, doc_type=doc_type, intento=attempt + 1):
            invalid: dict[str, Any] = {}
            doc: Documento | None = result.value
            if doc is None:
                doc, invalid = salvage(schema, result.raw, doc_type)
            validaciones = validar_documento(doc, hoy) if doc is not None else []
            fallidos = failed_fields(validaciones) | set(invalid)

        if doc is not None:
            score = len(fallidos)
            if best_score is None or score <= best_score:
                best_score = score
                out.documento = doc
                out.validaciones = validaciones
                out.invalid = invalid
                out.doubtful = fallidos
            if not fallidos:
                break
            errores = _feedback(validaciones, invalid)
        else:
            errores = f"- la salida no cumple el esquema: {(result.validation_error or '')[:1500]}"

        if llm.cap_exceeded:
            out.cap_exceeded = True
            break
        # Reintento: documento original + última respuesta + errores (el contexto no crece).
        messages = [
            *base,
            Message("assistant", json.dumps(result.raw or {}, ensure_ascii=False, default=str)),
            Message("user", prompt.render_retry(errores)),
        ]
    out.cap_exceeded = out.cap_exceeded or llm.cap_exceeded
    return out
