"""Documentos: carga, listado, detalle y archivo original (F0-12, #22)."""

import hashlib
import logging
import uuid
from pathlib import PurePath
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import select, update

from app.config import Settings, get_settings
from app.consent import accepted_at
from app.db.models import Document, ExtractedField, Extraction, LlmCall
from app.deps import CurrentPrincipal, DbSession, Enqueue, Storage
from app.files import InvalidFileError, validate
from app.governance import audit
from app.routers.consent import CurrentConsent
from app.routers.dto import DocumentDetailOut, DocumentOut, ExtractionOut, FieldOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


def _safe_filename(name: str | None) -> str:
    # Solo el nombre base (sin rutas del cliente), recortado a lo que cabe en la columna.
    base = PurePath((name or "").replace("\\", "/")).name.strip()
    return (base or "documento")[:255]


@router.post("", response_model=list[DocumentOut], status_code=status.HTTP_201_CREATED)
def upload_documents(
    files: Annotated[list[UploadFile], File(description="Uno o varios archivos")],
    db: DbSession,
    principal: CurrentPrincipal,
    storage: Storage,
    enqueue: Enqueue,
    settings: Annotated[Settings, Depends(get_settings)],
    consent: CurrentConsent,
) -> list[Document]:
    # Sin la autorización de uso de datos vigente aceptada, no se recibe ningún archivo.
    if accepted_at(db, principal.user_id, consent) is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Debes aceptar la autorización de uso de documentos antes de subir archivos.",
        )
    if not files:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No se envió ningún archivo.")
    if len(files) > settings.upload_max_files:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Máximo {settings.upload_max_files} archivos por carga.",
        )

    # 1) Validar TODOS antes de subir ninguno: la carga es todo o nada.
    validated = []
    for upload in files:
        data = upload.file.read(settings.upload_max_bytes + 1)
        filename = _safe_filename(upload.filename)
        try:
            detected = validate(data, settings.upload_max_bytes)
        except InvalidFileError as exc:
            code = (
                status.HTTP_413_CONTENT_TOO_LARGE
                if len(data) > settings.upload_max_bytes
                else status.HTTP_422_UNPROCESSABLE_CONTENT
            )
            raise HTTPException(code, f"{filename}: {exc}") from exc
        validated.append((filename, data, detected))

    # 2) Subir al almacenamiento y crear las filas en una sola transacción.
    org = principal.organization_id
    documents: list[Document] = []
    for filename, data, detected in validated:
        doc_id = uuid.uuid4()
        key = f"org/{org}/documents/{doc_id}{detected.extension}"
        storage.put(key, data, detected.content_type)
        doc = Document(
            id=doc_id,
            organization_id=org,
            uploaded_by=principal.user_id,
            filename=filename,
            content_type=detected.content_type,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            storage_key=key,
            status="queued",
        )
        db.add(doc)
        audit.record(
            db,
            organization_id=org,
            actor=principal.actor,
            action="document.uploaded",
            entity="documents",
            entity_id=doc_id,
            new_value={"filename": filename, "sha256": doc.sha256, "size_bytes": len(data)},
        )
        documents.append(doc)
    db.flush()
    db.commit()

    # 3) Encolar después del commit, para que el worker encuentre las filas.
    for doc in documents:
        try:
            enqueue(doc.id, org)
        except Exception:  # la carga ya quedó; el documento sigue en `queued` y puede reencolarse
            logger.exception("No se pudo encolar el documento %s", doc.id)
    return documents


@router.get("", response_model=list[DocumentOut])
def list_documents(db: DbSession, limit: int = 100, offset: int = 0) -> list[Document]:
    limit = max(1, min(limit, 500))
    stmt = (
        select(Document)
        .order_by(Document.created_at.desc(), Document.id)
        .limit(limit)
        .offset(max(0, offset))
    )
    docs = list(db.scalars(stmt))
    db.commit()
    return docs


def _get_document(db: DbSession, document_id: uuid.UUID) -> Document:
    # RLS: un documento de otra organización simplemente no existe para esta sesión.
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado.")
    return doc


@router.get("/{document_id}", response_model=DocumentDetailOut)
def get_document(document_id: uuid.UUID, db: DbSession) -> DocumentDetailOut:
    doc = _get_document(db, document_id)
    extraction = db.scalar(
        select(Extraction)
        .where(Extraction.document_id == doc.id)
        .order_by(Extraction.created_at.desc())
        .limit(1)
    )
    fields: list[ExtractedField] = []
    if extraction is not None:
        fields = list(
            db.scalars(
                select(ExtractedField)
                .where(ExtractedField.extraction_id == extraction.id)
                .order_by(ExtractedField.name)
            )
        )
    db.commit()
    return DocumentDetailOut(
        **DocumentOut.model_validate(doc).model_dump(),
        extraction=ExtractionOut.model_validate(extraction) if extraction else None,
        fields=[FieldOut.model_validate(f) for f in fields],
    )


@router.get("/{document_id}/file", response_class=Response)
def get_document_file(document_id: uuid.UUID, db: DbSession, storage: Storage) -> Response:
    doc = _get_document(db, document_id)
    db.commit()
    data = storage.get(doc.storage_key)
    return Response(
        content=data,
        media_type=doc.content_type,
        headers={
            "Content-Disposition": f'inline; filename="{doc.id}{PurePath(doc.storage_key).suffix}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal, storage: Storage
) -> Response:
    """Borra el archivo del almacenamiento y las filas del documento (extracción y campos).

    Orden: se bloquea y borra en la transacción, se borra el objeto y solo entonces se hace
    commit. Si falla el almacenamiento, no se borra nada en la BD; si falla el commit, el
    documento sigue y se puede reintentar (borrar un objeto ya borrado no falla en S3).
    `llm_calls` se conserva (costo y presupuesto) pero se desliga del documento. El evento de
    auditoría queda; no guarda el nombre del archivo.
    """
    doc = db.scalar(select(Document).where(Document.id == document_id).with_for_update())
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado.")
    old_value = {
        "sha256": doc.sha256,
        "size_bytes": doc.size_bytes,
        "content_type": doc.content_type,
        "status": doc.status,
        "doc_type": doc.doc_type,
    }
    db.execute(update(LlmCall).where(LlmCall.document_id == doc.id).values(document_id=None))
    db.delete(doc)
    audit.record(
        db,
        organization_id=principal.organization_id,
        actor=principal.actor,
        action="document.deleted",
        entity="documents",
        entity_id=doc.id,
        old_value=old_value,
    )
    db.flush()
    try:
        storage.delete(doc.storage_key)
    except Exception as exc:
        logger.exception("No se pudo borrar el archivo del documento %s", doc.id)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "No se pudo borrar el archivo; intenta de nuevo."
        ) from exc
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
