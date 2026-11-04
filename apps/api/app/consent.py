"""Autorización de uso de documentos (Ley 1581 de 2012) que se acepta antes de la primera carga.

El texto es `docs/legal/autorizacion-uso-documentos.md` (BORRADOR, pendiente de revisión de un
abogado). La versión que se guarda es la etiqueta `CONSENT_VERSION_LABEL` más el SHA-256 del
texto: si el texto cambia, la aceptación anterior deja de valer y hay que aceptar de nuevo.
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DataUseConsent


@dataclass(frozen=True, slots=True)
class ConsentDocument:
    version: str
    sha256: str
    text: str
    is_draft: bool


class ConsentUnavailableError(RuntimeError):
    """No se encontró el texto de la autorización: no se puede aceptar ni subir (falla cerrado)."""


@lru_cache(maxsize=4)
def _load(path: Path, label: str) -> ConsentDocument:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConsentUnavailableError(f"No se pudo leer {path.name}") from exc
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return ConsentDocument(
        version=f"{label}+{digest[:12]}",
        sha256=digest,
        text=text,
        is_draft="borrador" in text[:300].lower(),
    )


def load_consent_document(path: Path, label: str) -> ConsentDocument:
    return _load(path.resolve(), label)


def accepted_at(session: Session, user_id: uuid.UUID, document: ConsentDocument) -> datetime | None:
    """Fecha de aceptación del texto vigente, o None. Bajo RLS: solo la organización actual."""
    return session.scalar(
        select(DataUseConsent.accepted_at).where(
            DataUseConsent.user_id == user_id,
            DataUseConsent.text_sha256 == document.sha256,
        )
    )
