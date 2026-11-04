"""Las migraciones aplican limpio y dejan RLS activo y forzado en toda tabla de negocio."""

from sqlalchemy import Engine, inspect, text

from alembic import command
from app.db.models import TENANT_TABLES, Base
from tests.conftest import alembic_config

ALL_TABLES = {"organizations", *TENANT_TABLES}


def test_upgrade_creates_all_tables(owner_engine: Engine, migrated: None) -> None:
    tables = set(inspect(owner_engine).get_table_names())
    assert tables >= ALL_TABLES
    assert set(Base.metadata.tables) <= tables


def test_rls_enabled_and_forced(owner_engine: Engine, migrated: None) -> None:
    with owner_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = ANY(:t) AND relkind = 'r'"
            ),
            {"t": list(ALL_TABLES)},
        ).all()
    assert {r.relname for r in rows} == ALL_TABLES
    assert all(r.relrowsecurity and r.relforcerowsecurity for r in rows), rows


def test_tenant_tables_have_organization_id(owner_engine: Engine, migrated: None) -> None:
    insp = inspect(owner_engine)
    for table in TENANT_TABLES:
        columns = {c["name"]: c for c in insp.get_columns(table)}
        assert "organization_id" in columns, table
        assert columns["organization_id"]["nullable"] is False, table


def test_app_role_cannot_bypass_rls(owner_engine: Engine, migrated: None) -> None:
    with owner_engine.connect() as conn:
        row = conn.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'contable_app'")
        ).one()
    assert row.rolsuper is False
    assert row.rolbypassrls is False


def test_audit_events_privileges(owner_engine: Engine, migrated: None) -> None:
    with owner_engine.connect() as conn:
        privs = {
            p: conn.execute(
                text("SELECT has_table_privilege('contable_app', 'audit_events', :p)"), {"p": p}
            ).scalar_one()
            for p in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")
        }
    assert privs == {
        "SELECT": True,
        "INSERT": True,
        "UPDATE": False,
        "DELETE": False,
        "TRUNCATE": False,
    }


def test_downgrade_and_upgrade_roundtrip(owner_engine: Engine, migrated: None) -> None:
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    assert not (ALL_TABLES & set(inspect(owner_engine).get_table_names()))
    command.upgrade(cfg, "head")
    assert set(inspect(owner_engine).get_table_names()) >= ALL_TABLES
