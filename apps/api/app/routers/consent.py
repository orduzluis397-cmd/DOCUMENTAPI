"""Autorización de uso de documentos: consultar el texto vigente y aceptarlo (CR-005)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import Settings, get_settings
from app.consent import (
    ConsentDocument,
    ConsentUnavailableError,
    accepted_at,
    load_consent_document,
)
from app.db.models import DataUseConsent
from app.deps import CurrentPrincipal, DbSession
from app.governance import audit

router = APIRouter(prefix="/consent", tags=["consent"])


class ConsentOut(BaseModel):
    version: str
    sha256: str
    is_draft: bool
    text: str
    accepted: bool
    accepted_at: datetime | None


class ConsentAcceptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # La versión que el usuario vio en pantalla; si el texto cambió entretanto → 409.
    version: str


def get_consent_document(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ConsentDocument:
    try:
        return load_consent_document(settings.consent_document_path, settings.consent_version_label)
    except ConsentUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "La autorización de uso de datos no está disponible; no se pueden subir documentos.",
        ) from exc


CurrentConsent = Annotated[ConsentDocument, Depends(get_consent_document)]


def _out(doc: ConsentDocument, when: datetime | None) -> ConsentOut:
    return ConsentOut(
        version=doc.version,
        sha256=doc.sha256,
        is_draft=doc.is_draft,
        text=doc.text,
        accepted=when is not None,
        accepted_at=when,
    )


@router.get("", response_model=ConsentOut)
def get_consent(db: DbSession, principal: CurrentPrincipal, doc: CurrentConsent) -> ConsentOut:
    when = accepted_at(db, principal.user_id, doc)
    db.commit()
    return _out(doc, when)


@router.post("", response_model=ConsentOut, status_code=status.HTTP_201_CREATED)
def accept_consent(
    body: ConsentAcceptIn, db: DbSession, principal: CurrentPrincipal, doc: CurrentConsent
) -> ConsentOut:
    if body.version != doc.version:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "El texto de la autorización cambió. Vuelve a leerlo antes de aceptar.",
        )
    created_id = db.scalar(
        pg_insert(DataUseConsent)
        .values(
            organization_id=principal.organization_id,
            user_id=principal.user_id,
            version=doc.version,
            text_sha256=doc.sha256,
        )
        .on_conflict_do_nothing()
        .returning(DataUseConsent.id)
    )
    if created_id is not None:
        # Misma transacción que la aceptación (regla dura 5).
        audit.record(
            db,
            organization_id=principal.organization_id,
            actor=principal.actor,
            action="consent.accepted",
            entity="data_use_consents",
            entity_id=created_id,
            new_value={"version": doc.version, "text_sha256": doc.sha256},
        )
    when = accepted_at(db, principal.user_id, doc)
    db.commit()
    return _out(doc, when)
