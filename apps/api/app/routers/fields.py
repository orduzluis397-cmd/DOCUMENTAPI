"""Corrección humana de campos extraídos (F0-12, #22).

La corrección y su evento de auditoría se escriben en la MISMA transacción (regla dura 5): si
el evento no se puede guardar, el campo tampoco cambia.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.db.models import ExtractedField, Extraction
from app.deps import CurrentPrincipal, DbSession
from app.governance import audit
from app.routers.dto import FieldCorrectionIn, FieldOut

router = APIRouter(prefix="/fields", tags=["fields"])


@router.patch("/{field_id}", response_model=FieldOut)
def correct_field(
    field_id: uuid.UUID,
    body: FieldCorrectionIn,
    db: DbSession,
    principal: CurrentPrincipal,
) -> ExtractedField:
    field = db.scalar(select(ExtractedField).where(ExtractedField.id == field_id).with_for_update())
    if field is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campo no encontrado.")
    extraction = db.get(Extraction, field.extraction_id)

    old = {"value": field.value, "corrected_value": field.corrected_value}
    field.corrected_value = body.corrected_value
    field.corrected_by = principal.user_id
    field.corrected_at = datetime.now(UTC)

    audit.record(
        db,
        organization_id=principal.organization_id,
        actor=principal.actor,
        action="field.corrected",
        entity="extracted_fields",
        entity_id=field.id,
        old_value=old,
        new_value={"corrected_value": body.corrected_value, "name": field.name},
        model=extraction.model if extraction else None,
        prompt_version=extraction.prompt_version if extraction else None,
        trace_id=extraction.trace_id if extraction else None,
    )
    db.flush()
    db.commit()
    return field
