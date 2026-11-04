"""Puntos de instrumentación de trazas (preparados para la semana 4, INSTRUCCIONES.md §9).

Hoy `span` no envía nada: solo fija los nombres de los pasos (`clasificar`, `ocr`, `extraer`,
`validar`, `reintentar`) y sus metadatos en un único lugar. En la semana 4 se reemplaza
`NoopTracer` por Langfuse (`@observe`) u OpenTelemetry + OpenInference sin tocar el extractor:
el `trace_id` por documento ya existe y se guarda en `extractions` y `llm_calls`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any, Literal, Protocol

SpanName = Literal[
    "documento", "clasificar", "pdf_texto", "ocr", "xml", "extraer", "validar", "reintentar"
]


class Tracer(Protocol):
    def span(
        self, name: SpanName, trace_id: str, **attributes: Any
    ) -> AbstractContextManager[None]: ...


class NoopTracer:
    @contextmanager
    def span(self, name: SpanName, trace_id: str, **attributes: Any) -> Iterator[None]:
        yield


_tracer: Tracer = NoopTracer()


def get_tracer() -> Tracer:
    return _tracer


def set_tracer(tracer: Tracer) -> None:
    global _tracer  # punto único de reemplazo (semana 4)
    _tracer = tracer
