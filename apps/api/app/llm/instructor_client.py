"""Cliente LLM con Instructor (salida estructurada al esquema Pydantic del tipo de documento).

Instructor se usa con `max_retries=0` (un intento por llamada): los reintentos los hace el
extractor, para que **cada** intento se registre en `llm_calls` y respete el tope de costo.
"""

from __future__ import annotations

import json
from typing import Any

import instructor
from instructor.core.exceptions import InstructorRetryException
from pydantic import BaseModel

from app.llm.base import (
    EXTRACTION_TEMPERATURE,
    LLMError,
    LLMUsage,
    Message,
    StructuredResult,
)


class InstructorLLMClient:
    """Envuelve un cliente de Instructor (`from_openai`, `from_anthropic`)."""

    def __init__(
        self,
        provider: str,
        client: instructor.Instructor,
        *,
        max_output_tokens: int | None = None,
        max_tokens_param: str = "max_tokens",
    ) -> None:
        self._provider = provider
        self._client = client
        self._max_output_tokens = max_output_tokens
        self._max_tokens_param = max_tokens_param

    @property
    def provider(self) -> str:
        return self._provider

    def structured[T: BaseModel](
        self, *, model: str, messages: list[Message], response_model: type[T]
    ) -> StructuredResult[T]:
        kwargs: dict[str, Any] = {}
        if self._max_output_tokens is not None:
            kwargs[self._max_tokens_param] = self._max_output_tokens
        try:
            value, completion = self._client.chat.completions.create_with_completion(
                model=model,
                messages=[{"role": m.role, "content": m.content} for m in messages],  # type: ignore[misc]
                response_model=response_model,
                max_retries=0,
                temperature=EXTRACTION_TEMPERATURE,
                **kwargs,
            )
        except InstructorRetryException as exc:
            if exc.last_completion is None:
                raise LLMError(f"{type(exc).__name__}: {exc}") from exc
            return StructuredResult(
                value=None,
                raw=raw_json(exc.last_completion),
                usage=usage_of(exc.last_completion),
                model=model,
                validation_error=_short_error(exc),
            )
        except Exception as exc:  # errores del SDK del proveedor (red, 4xx, 5xx)
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc
        return StructuredResult(
            value=value, raw=raw_json(completion), usage=usage_of(completion), model=model
        )


def usage_of(completion: Any) -> LLMUsage:
    """Tokens de una respuesta OpenAI (`prompt_tokens`) o Anthropic (`input_tokens`)."""
    usage = getattr(completion, "usage", None)
    if usage is None:
        return LLMUsage()
    inp = getattr(usage, "input_tokens", None) or getattr(usage, "prompt_tokens", 0) or 0
    out = getattr(usage, "output_tokens", None) or getattr(usage, "completion_tokens", 0) or 0
    return LLMUsage(input_tokens=int(inp), output_tokens=int(out))


def raw_json(completion: Any) -> dict[str, Any] | None:
    """JSON de la llamada a herramienta (OpenAI `tool_calls`, Anthropic `tool_use`) o del texto."""
    choices = getattr(completion, "choices", None)
    if choices:
        message = choices[0].message
        for call in getattr(message, "tool_calls", None) or []:
            parsed = _loads(call.function.arguments)
            if parsed is not None:
                return parsed
        return _loads(getattr(message, "content", None))
    for block in getattr(completion, "content", None) or []:
        if getattr(block, "type", None) == "tool_use" and isinstance(block.input, dict):
            return dict(block.input)
        if getattr(block, "type", None) == "text":
            parsed = _loads(block.text)
            if parsed is not None:
                return parsed
    return None


def _loads(text: Any) -> dict[str, Any] | None:
    if not isinstance(text, str):
        return None
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _short_error(exc: InstructorRetryException) -> str:
    last = getattr(exc, "failed_attempts", None) or []
    if last:
        return str(last[-1].exception)[:2000]
    return str(exc)[:2000]
