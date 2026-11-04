"""Interfaz del cliente LLM (F0-10, #20).

El resto de la app solo conoce `LLMClient`: un intento de salida estructurada por llamada. Los
reintentos, el tope de costo y el registro en `llm_calls` viven fuera del cliente
(`app.observability.llm_calls.TrackedLLM`) para que cada intento quede registrado por separado.

La temperatura de las extracciones es **fija** (`EXTRACTION_TEMPERATURE`): no es un parámetro
de la interfaz ni una variable de entorno (INSTRUCCIONES.md §5.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Protocol

from pydantic import BaseModel

EXTRACTION_TEMPERATURE: Final = 0.0


class LLMError(Exception):
    """Error del proveedor (red, autenticación, cuota…): el intento no produjo respuesta."""


class LLMNotConfiguredError(LLMError):
    """Falta configuración (proveedor, modelo, clave, tope de costo o precio)."""


@dataclass(frozen=True, slots=True)
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True, slots=True)
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True, slots=True)
class StructuredResult[T: BaseModel]:
    """Resultado de UN intento.

    - `value`: objeto validado por Pydantic, o `None` si la salida no pasó el esquema.
    - `raw`: JSON crudo que devolvió el modelo (sirve para rescatar campos válidos).
    - `validation_error`: mensaje de Pydantic cuando `value` es `None`.
    """

    value: T | None
    raw: dict[str, Any] | None
    usage: LLMUsage
    model: str
    validation_error: str | None = None


class LLMClient(Protocol):
    @property
    def provider(self) -> str: ...

    def structured[T: BaseModel](
        self, *, model: str, messages: list[Message], response_model: type[T]
    ) -> StructuredResult[T]:
        """Un solo intento, con `temperature=EXTRACTION_TEMPERATURE`. Lanza `LLMError`."""
        ...
