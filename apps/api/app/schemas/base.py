"""Base común de los esquemas de documentos."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class EsquemaBase(BaseModel):
    """Campos desconocidos se rechazan; los textos se recortan. Ausente = ``None`` (GUIA.md)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)
