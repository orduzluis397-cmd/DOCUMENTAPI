"""Modelos SQLAlchemy 2 de Contable IA (INSTRUCCIONES.md §8.3).

Toda tabla de negocio lleva `organization_id` y tiene Row Level Security activo y forzado
(la política está en la migración, no aquí). Las tablas hijas referencian a su padre con una
clave compuesta `(id, organization_id)`, de modo que una fila nunca puede apuntar a otra
organización aunque alguien inserte con el rol dueño.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, get_args

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Nombres de restricciones estables para que Alembic genere migraciones deterministas.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

DocumentStatus = Literal["queued", "processing", "extracted", "needs_review", "failed"]
DOCUMENT_STATUSES: tuple[str, ...] = get_args(DocumentStatus)

ExtractionMethod = Literal["xml_parser", "pdf_text", "ocr", "llm"]
EXTRACTION_METHODS: tuple[str, ...] = get_args(ExtractionMethod)

LlmCallStatus = Literal["ok", "error"]
LLM_CALL_STATUSES: tuple[str, ...] = get_args(LlmCallStatus)


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def _org_fk() -> Mapped[uuid.UUID]:
    return mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    nit: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = _created_at()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("organization_id", "email"),
        UniqueConstraint("id", "organization_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="member")
    # Identificador del proveedor de autenticación (Clerk/Auth.js), pendiente de F0-13+.
    external_auth_id: Mapped[str | None] = mapped_column(String(200), unique=True)
    created_at: Mapped[datetime] = _created_at()


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("id", "organization_id"),
        ForeignKeyConstraint(
            ["uploaded_by", "organization_id"], ["users.id", "users.organization_id"]
        ),
        CheckConstraint(f"status IN ({_in(DOCUMENT_STATUSES)})", name="status"),
        CheckConstraint("size_bytes >= 0", name="size_bytes"),
        Index("ix_documents_org_created", "organization_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    doc_type: Mapped[str | None] = mapped_column(String(50))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Extraction(Base):
    __tablename__ = "extractions"
    __table_args__ = (
        UniqueConstraint("id", "organization_id"),
        ForeignKeyConstraint(
            ["document_id", "organization_id"],
            ["documents.id", "documents.organization_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(f"method IN ({_in(EXTRACTION_METHODS)})", name="method"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    doc_type: Mapped[str | None] = mapped_column(String(50))
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    schema_version: Mapped[str | None] = mapped_column(String(50))
    trace_id: Mapped[str | None] = mapped_column(String(64))
    raw_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    created_at: Mapped[datetime] = _created_at()


class ExtractedField(Base):
    __tablename__ = "extracted_fields"
    __table_args__ = (
        UniqueConstraint("extraction_id", "name"),
        ForeignKeyConstraint(
            ["extraction_id", "organization_id"],
            ["extractions.id", "extractions.organization_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["corrected_by", "organization_id"], ["users.id", "users.organization_id"]
        ),
        CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1", name="confidence"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    extraction_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    # Ruta del campo en el esquema, p. ej. "emisor.nit" o "items[0].valor".
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[Any | None] = mapped_column(JSONB)
    corrected_value: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True))
    is_doubtful: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4, asdecimal=False))
    page: Mapped[int | None] = mapped_column(Integer)
    corrected_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


class LlmCall(Base):
    """Una fila por llamada a un LLM (regla dura 9). La escritura llega con F0-10."""

    __tablename__ = "llm_calls"
    __table_args__ = (
        CheckConstraint(f"status IN ({_in(LLM_CALL_STATUSES)})", name="status"),
        CheckConstraint("input_tokens >= 0 AND output_tokens >= 0", name="tokens"),
        CheckConstraint("cost_usd >= 0", name="cost_usd"),
        CheckConstraint("latency_ms >= 0", name="latency_ms"),
        ForeignKeyConstraint(
            ["document_id", "organization_id"],
            ["documents.id", "documents.organization_id"],
            ondelete="RESTRICT",
        ),
        Index("ix_llm_calls_org_created", "organization_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    purpose: Mapped[str | None] = mapped_column(String(50))  # clasificación, extracción, juez…
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=Decimal(0))
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="ok")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class AuditEvent(Base):
    """Evento de auditoría inmutable (regla dura 5).

    El rol de la app no tiene UPDATE/DELETE sobre esta tabla y un trigger rechaza ambas
    operaciones incluso para el dueño. Se escribe en la misma transacción que el cambio.
    """

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_entity", "organization_id", "entity", "entity_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organization_id: Mapped[uuid.UUID] = _org_fk()
    # "user:<uuid>", "system:worker", "model:<nombre>"…
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True))
    new_value: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True))
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    trace_id: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# Tablas de negocio con RLS por organization_id (la migración las recorre).
TENANT_TABLES: tuple[str, ...] = (
    "users",
    "documents",
    "extractions",
    "extracted_fields",
    "llm_calls",
    "audit_events",
)
