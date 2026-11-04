"""Login con Clerk, autorización de uso de datos y cierre de la API pública de Supabase (CR-005).

- `organizations.external_auth_id` (id de Clerk `org_...`, único).
- `users.external_auth_id` deja de ser único global: un usuario de Clerk puede estar en varias
  organizaciones (una fila por organización). Único por `(organization_id, external_auth_id)`.
- `data_use_consents`: aceptación de la autorización de uso de documentos (versión y SHA-256
  del texto). RLS activo y forzado; el rol de la app solo SELECT/INSERT (prueba de aceptación,
  no se edita ni se borra desde la app).
- Si existen los roles `anon` y `authenticated` (Supabase), se les revoca todo sobre las tablas,
  secuencias y funciones del esquema. La función del trigger de auditoría deja de ser
  ejecutable por PUBLIC (no hace falta: los triggers no comprueban EXECUTE al dispararse).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-04 18:00:00
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# NULLIF: ver 0001 (sin contexto de organización, ninguna fila es visible).
CURRENT_ORG = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
SUPABASE_API_ROLES = ("anon", "authenticated")


def _app_role() -> str:
    role = os.environ.get("POSTGRES_APP_USER", "contable_app")
    if not role.replace("_", "").isalnum():
        raise ValueError(f"Nombre de rol inválido: {role!r}")
    return role


def revoke_supabase_api_roles() -> None:
    """Quita a `anon`/`authenticated` todo privilegio sobre los objetos de `public`."""
    for role in SUPABASE_API_ROLES:
        op.execute(
            f"""
            DO $$
            BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role};
                REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {role};
                REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM {role};
              END IF;
            END
            $$
            """  # noqa: S608 - nombres de rol constantes
        )


def upgrade() -> None:
    op.add_column(
        "organizations", sa.Column("external_auth_id", sa.String(length=200), nullable=True)
    )
    op.create_unique_constraint(
        op.f("uq_organizations_external_auth_id"), "organizations", ["external_auth_id"]
    )
    op.drop_constraint(op.f("uq_users_external_auth_id"), "users", type_="unique")
    op.create_unique_constraint(
        op.f("uq_users_organization_id_external_auth_id"),
        "users",
        ["organization_id", "external_auth_id"],
    )

    op.create_table(
        "data_use_consents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_data_use_consents_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name=op.f("fk_data_use_consents_user_id_organization_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_use_consents")),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            "text_sha256",
            name=op.f("uq_data_use_consents_organization_id_user_id_text_sha256"),
        ),
    )
    op.create_index(
        op.f("ix_data_use_consents_organization_id"),
        "data_use_consents",
        ["organization_id"],
        unique=False,
    )
    op.execute("ALTER TABLE data_use_consents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE data_use_consents FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_select ON data_use_consents FOR SELECT "
        f"USING (organization_id = {CURRENT_ORG})"
    )
    op.execute(
        "CREATE POLICY tenant_insert ON data_use_consents FOR INSERT "
        f"WITH CHECK (organization_id = {CURRENT_ORG})"
    )

    role = _app_role()
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
            REVOKE ALL ON data_use_consents FROM "{role}";
            GRANT SELECT, INSERT ON data_use_consents TO "{role}";
          END IF;
        END
        $$
        """  # noqa: S608 - rol validado en _app_role
    )
    op.execute("REVOKE ALL ON FUNCTION audit_events_reject_change() FROM PUBLIC")
    revoke_supabase_api_roles()


def downgrade() -> None:
    op.execute("GRANT EXECUTE ON FUNCTION audit_events_reject_change() TO PUBLIC")
    op.drop_index(op.f("ix_data_use_consents_organization_id"), table_name="data_use_consents")
    op.drop_table("data_use_consents")
    op.drop_constraint(op.f("uq_users_organization_id_external_auth_id"), "users", type_="unique")
    # El esquema anterior exigía un solo usuario por id de Clerk: las filas extra de un mismo
    # usuario en otras organizaciones pierden el vínculo (se conserva el más antiguo).
    op.execute(
        """
        UPDATE users u SET external_auth_id = NULL
        WHERE external_auth_id IS NOT NULL AND EXISTS (
          SELECT 1 FROM users o
          WHERE o.external_auth_id = u.external_auth_id
            AND (o.created_at, o.id) < (u.created_at, u.id)
        )
        """
    )
    op.create_unique_constraint(op.f("uq_users_external_auth_id"), "users", ["external_auth_id"])
    op.drop_constraint(op.f("uq_organizations_external_auth_id"), "organizations", type_="unique")
    op.drop_column("organizations", "external_auth_id")
