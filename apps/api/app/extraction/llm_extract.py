"""Clasificación y extracción con LLM (Instructor), con reintentos acotados y campos dudosos.

Cada intento es una llamada registrada en `llm_calls` (vía `TrackedLLM`). Un intento falla si
la salida no pasa el esquema Pydantic o los validadores de dominio (`app.schemas.validators`).
El reintento le dice al modelo **qué regla y qué campos** fallaron, nunca el valor calculado
(GUIA.md §2: se copia el valor tal como aparece; el validador es quien detecta el error).

Un reintento no puede "borrar" una duda: todo campo que falló en algún intento queda
`is_doubtful=true` si su valor final es null o distinto del que falló (y con él los demás campos
de la misma regla). El mejor intento se elige penalizando los campos que antes tenían valor y
quedaron en null.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.extraction.fields import failed_fields, flatten, in_scope, salvage
from app.extraction.prompts import Prompt, load_prompt, wrap_document
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


def _base_messages(prompt: Prompt, text: str, **values: str) -> list[Message]:
    """Mensajes del primer intento con una etiqueta nueva (nonce) en cada llamada."""
    tag, safe = wrap_document(text)
    return [
        Message("system", prompt.system),
        Message("user", prompt.render_user(etiqueta=tag, texto=safe, **values)),
    ]


def classify(text: str, llm: TrackedLLM, *, model: str, max_retries: int) -> DocType:
    prompt = load_prompt("clasificacion")
    last_error = ""
    retry: list[Message] = []
    for attempt in range(1 + max_retries):
        messages = _base_messages(prompt, text) + retry
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
        # El reintento no repite los mismos mensajes: agrega la respuesta y el motivo.
        retry = [
            Message("assistant", json.dumps(result.raw or {}, ensure_ascii=False, default=str)),
            Message("user", prompt.render_retry("tipo_documento no es uno de los 5 tipos.")),
        ]
    raise ExtractionError(f"No se pudo clasificar el documento: {last_error[:300]}")


def _feedback(validaciones: list[ResultadoValidacion], invalid: dict[str, Any]) -> str:
    """Solo regla y campos. Nunca el valor esperado o calculado."""
    lines: list[str] = []
    for v in validaciones:
        if v.ok or v.severidad != "error":
            continue
        campos = ", ".join(v.campos)
        if v.regla == "dv_nit":
            lines.append(f"- {campos}: relee el NIT y su DV tal como aparecen en el documento.")
        else:
            lines.append(f"- regla {v.regla} ({campos}): relee estos campos en el documento.")
    lines += [
        f"- {campo}: el valor no tiene el formato del esquema; relee el campo." for campo in invalid
    ]
    return "\n".join(lines)


def _snapshot(flat: dict[str, Any], campo: str) -> str:
    items = sorted((k, v) for k, v in flat.items() if in_scope(k, (campo,)))
    return json.dumps(items, ensure_ascii=False, default=str)


def _has_value(flat: dict[str, Any], campo: str) -> bool:
    return any(v not in (None, []) for k, v in flat.items() if in_scope(k, (campo,)))


@dataclass
class _Failure:
    """Una regla (o campo de esquema) que falló en un intento y el valor que tenía entonces."""

    campos: tuple[str, ...]
    snapshots: dict[str, str]


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
    instrucciones = prompt.tipos.get(doc_type, "")
    out = LlmExtraction(doc_type=doc_type, documento=None, prompt_version=prompt.version)
    best_score: int | None = None
    best_flat: dict[str, Any] = {}
    failures: list[_Failure] = []
    present_before: set[str] = set()
    retry: list[Message] = []
    tracer = get_tracer()

    for attempt in range(1 + max_retries):
        messages = _base_messages(prompt, text, tipo=doc_type, instrucciones=instrucciones) + retry
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
            flat = dict(flatten(doc))
            # Historial de fallas con el valor que tenía cada campo al fallar.
            for v in validaciones:
                if not v.ok and v.severidad == "error":
                    failures.append(_Failure(v.campos, {c: _snapshot(flat, c) for c in v.campos}))
            for campo, original in invalid.items():
                failures.append(
                    _Failure((campo,), {campo: json.dumps([[campo, original]], default=str)})
                )
            # Puntaje: campos que fallan + campos que tenían valor antes y ahora son null.
            vaciados = {p for p in present_before if flat.get(p) in (None, [])}
            score = len(fallidos) + len(vaciados)
            if best_score is None or score <= best_score:
                best_score = score
                best_flat = flat
                out.documento = doc
                out.validaciones = validaciones
                out.invalid = invalid
                out.doubtful = set(fallidos)
            present_before |= {p for p, val in flat.items() if val not in (None, [])}
            if not fallidos:
                break
            errores = _feedback(validaciones, invalid)
        else:
            errores = (
                "- la salida no cumple el esquema JSON pedido: "
                f"{(result.validation_error or '')[:1500]}"
            )

        if llm.cap_exceeded:
            out.cap_exceeded = True
            break
        # Reintento: documento + última respuesta + errores (el contexto no crece).
        retry = [
            Message("assistant", json.dumps(result.raw or {}, ensure_ascii=False, default=str)),
            Message("user", prompt.render_retry(errores)),
        ]

    if out.documento is not None:
        for failure in failures:
            changed = any(
                _snapshot(best_flat, c) != snap or not _has_value(best_flat, c)
                for c, snap in failure.snapshots.items()
            )
            if changed:
                out.doubtful |= set(failure.campos)
    out.cap_exceeded = out.cap_exceeded or llm.cap_exceeded
    return out
