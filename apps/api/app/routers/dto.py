"""Modelos Pydantic de entrada/salida de la API (frontera HTTP).

Los esquemas de dominio (Factura, RUT…) viven en `app/schemas/` y los mantiene `datos-corpus`;
aquí solo está la forma de las respuestas HTTP.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, JsonValue


class _Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DocumentOut(_Orm):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    status: str
    doc_type: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class FieldOut(_Orm):
    id: uuid.UUID
    extraction_id: uuid.UUID
    name: str
    value: JsonValue
    corrected_value: JsonValue
    is_doubtful: bool
    confidence: float | None
    page: int | None
    corrected_by: uuid.UUID | None
    corrected_at: datetime | None


class ExtractionOut(_Orm):
    id: uuid.UUID
    doc_type: str | None
    method: str
    model: str | None
    prompt_version: str | None
    created_at: datetime


class DocumentDetailOut(DocumentOut):
    extraction: ExtractionOut | None
    fields: list[FieldOut]


class FieldCorrectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corrected_value: JsonValue
