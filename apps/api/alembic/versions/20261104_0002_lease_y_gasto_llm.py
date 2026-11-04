"""Lease de procesamiento y gasto LLM global para el presupuesto (F0-10, #20).

- `documents.processing_started_at`: el worker reclama un documento de forma atómica y solo
  lo puede retomar otro worker cuando el lease vence (reentrega de Celery tras una caída).
- `llm_spend_usd_since(since)`: suma de `llm_calls.cost_usd` de TODAS las organizaciones desde
  `since`, para aplicar `LLM_DAILY_BUDGET_USD` y `LLM_MONTHLY_BUDGET_USD`. Devuelve solo el
  agregado. Es SECURITY DEFINER con dueño `contable_budget` (NOLOGIN, sin BYPASSRLS), que lee
  `llm_calls` por una política propia `USING (true)` limitada a las columnas `cost_usd` y
  `created_at`. Así no depende de que el dueño del esquema sea superusuario (Neon/Supabase).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-04 12:00:00
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BUDGET_ROLE = "contable_budget"


def _app_role() -> str:
    role = os.environ.get("POSTGRES_APP_USER", "contable_app")
    if not role.replace("_", "").isalnum():
        raise ValueError(f"Nombre de rol inválido: {role!r}")
    return role


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    role = _app_role()
    op.execute(
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{BUDGET_ROLE}') THEN
            CREATE ROLE {BUDGET_ROLE} NOLOGIN NOINHERIT;
          END IF;
        END
        $$
        """  # noqa: S608 - nombre de rol constante
    )
    # El que migra debe poder asignar el dueño de la función (sin ser superusuario).
    op.execute(f"GRANT {BUDGET_ROLE} TO CURRENT_USER")
    op.execute(f"GRANT SELECT (cost_usd, created_at) ON llm_calls TO {BUDGET_ROLE}")
    op.execute(f"CREATE POLICY budget_read ON llm_calls FOR SELECT TO {BUDGET_ROLE} USING (true)")
    op.execute(
        """
        CREATE FUNCTION llm_spend_usd_since(since timestamptz) RETURNS numeric
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
          SELECT COALESCE(SUM(cost_usd), 0) FROM public.llm_calls WHERE created_at >= since
        $$
        """
    )
    # ALTER OWNER exige que el nuevo dueño tenga CREATE en el esquema (si quien migra no es
    # superusuario); se concede solo mientras dura el cambio de dueño.
    op.execute(f"GRANT USAGE, CREATE ON SCHEMA public TO {BUDGET_ROLE}")
    op.execute(f"ALTER FUNCTION llm_spend_usd_since(timestamptz) OWNER TO {BUDGET_ROLE}")
    op.execute(f"REVOKE CREATE ON SCHEMA public FROM {BUDGET_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION llm_spend_usd_since(timestamptz) FROM PUBLIC")
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
            GRANT EXECUTE ON FUNCTION llm_spend_usd_since(timestamptz) TO "{role}";
          END IF;
        END
        $$
        """  # noqa: S608 - rol validado en _app_role
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS llm_spend_usd_since(timestamptz)")
    op.execute("DROP POLICY IF EXISTS budget_read ON llm_calls")
    op.execute(f"REVOKE ALL ON llm_calls FROM {BUDGET_ROLE}")
    op.execute(f"REVOKE ALL ON SCHEMA public FROM {BUDGET_ROLE}")
    # El rol es del clúster (lo pueden usar otras bases): no se borra aquí.
    op.drop_column("documents", "processing_started_at")
