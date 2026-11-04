"""Simulación de Supabase en el Postgres local: bootstrap.sql + migraciones sin superusuario.

Se crea una base aparte (`contable_ia_supabase_sim`) cuyo dueño es un rol como el `postgres` de
Supabase: LOGIN, CREATEROLE, BYPASSRLS, **sin** superusuario. Se imitan los permisos que
Supabase da por defecto a `anon` y `authenticated` (USAGE en public y ALL por defecto sobre
tablas, secuencias y funciones). Luego, como ese rol: bootstrap.sql → `alembic upgrade head` →
bootstrap.sql otra vez (como hace deploy.yml). Se comprueba que:

- las migraciones (incluida la 0002 con CREATE ROLE y SECURITY DEFINER) corren sin superusuario;
- `anon` y `authenticated` no tienen ningún privilegio sobre public;
- el rol de la app sigue bajo RLS y puede usar la función de presupuesto.

Limitación conocida: en este clúster el rol `contable_budget` ya lo creó otro rol (las pruebas
principales), así que se le da ADMIN OPTION al rol simulado, que es lo que tiene en Supabase el
rol que lo crea (PostgreSQL 16+).
"""

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

from alembic import command
from tests.conftest import DB_URL, DB_URL_MIGRATIONS, alembic_config

SIM_DB = "contable_ia_supabase_sim"
SIM_OWNER = "supabase_sim_owner"
SIM_PASSWORD = "supabase_sim_local"  # noqa: S105 - solo para esta base local de prueba
API_ROLES = ("anon", "authenticated")
BOOTSTRAP = Path(__file__).resolve().parents[3] / "infra/deploy/supabase/bootstrap.sql"


def _url(base: str, *, user: str | None = None, password: str | None = None) -> str:
    url = make_url(base).set(database=SIM_DB)
    if user is not None:
        url = url.set(username=user, password=password)
    return url.render_as_string(hide_password=False)


def _create_role(conn: Connection, name: str, attrs: str) -> None:
    exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :n"), {"n": name}).first()
    if exists is None:
        conn.execute(text(f"CREATE ROLE {name} {attrs}"))


def _run_script(engine: Engine, sql: str) -> None:
    # Directo con psycopg y sin parámetros: el script lleva `%I` de format() en los DO.
    raw = engine.raw_connection()
    try:
        driver = raw.driver_connection
        assert driver is not None
        driver.execute(sql)
    finally:
        raw.close()


@pytest.fixture(scope="module")
def supabase_sim(owner_engine: Engine, migrated: None) -> Iterator[dict[str, str]]:
    with owner_engine.connect() as conn:
        if not conn.execute(
            text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        ).scalar():
            pytest.skip("La simulación necesita un rol superusuario local para preparar la base")
    admin = owner_engine.execution_options(isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        for role in API_ROLES:
            _create_role(conn, role, "NOLOGIN")
        _create_role(conn, SIM_OWNER, "LOGIN")
        conn.execute(
            text(
                f"ALTER ROLE {SIM_OWNER} LOGIN NOSUPERUSER CREATEROLE CREATEDB BYPASSRLS "
                f"PASSWORD '{SIM_PASSWORD}'"
            )
        )
        conn.execute(text("GRANT contable_budget TO " + SIM_OWNER + " WITH ADMIN OPTION"))
        conn.execute(text(f"DROP DATABASE IF EXISTS {SIM_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {SIM_DB} OWNER {SIM_OWNER}"))

    # Permisos por defecto de Supabase para la Data API (lo que bootstrap.sql debe deshacer).
    su_sim = create_engine(_url(DB_URL_MIGRATIONS), isolation_level="AUTOCOMMIT")
    with su_sim.connect() as conn:
        roles = ", ".join(API_ROLES)
        conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {roles}"))
        for kind in ("TABLES", "SEQUENCES", "FUNCTIONS"):
            conn.execute(
                text(
                    f"ALTER DEFAULT PRIVILEGES FOR ROLE {SIM_OWNER} IN SCHEMA public "
                    f"GRANT ALL ON {kind} TO {roles}"
                )
            )
    su_sim.dispose()

    owner_url = _url(DB_URL_MIGRATIONS, user=SIM_OWNER, password=SIM_PASSWORD)
    sim_owner = create_engine(owner_url, isolation_level="AUTOCOMMIT")
    sql = BOOTSTRAP.read_text(encoding="utf-8")
    _run_script(sim_owner, sql)
    cfg = alembic_config()
    cfg.attributes["sqlalchemy.url"] = owner_url
    command.upgrade(cfg, "head")
    _run_script(sim_owner, sql)  # segunda pasada: idempotente
    sim_owner.dispose()

    yield {"owner": owner_url, "app": _url(DB_URL), "superuser": _url(DB_URL_MIGRATIONS)}

    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {SIM_DB} WITH (FORCE)"))


def test_owner_is_not_superuser(supabase_sim: dict[str, str]) -> None:
    engine = create_engine(supabase_sim["owner"])
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT rolsuper, rolcreaterole, rolbypassrls FROM pg_roles "
                "WHERE rolname = current_user"
            )
        ).one()
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()
    assert (row.rolsuper, row.rolcreaterole, row.rolbypassrls) == (False, True, True)
    assert version == "0003"


def test_api_roles_have_no_privileges(supabase_sim: dict[str, str]) -> None:
    engine = create_engine(supabase_sim["superuser"])
    with engine.connect() as conn:
        for role in API_ROLES:
            # Sin GRANT explícito sobre el esquema. (USAGE puede seguir llegando por PUBLIC, como
            # en todo PostgreSQL >= 15; no se toca para no romper roles internos de Supabase.
            # Lo que importa es que no hay privilegios sobre ningún objeto.)
            acl = conn.execute(
                text("SELECT coalesce(nspacl::text, '') FROM pg_namespace WHERE nspname = 'public'")
            ).scalar_one()
            assert f"{role}=" not in acl, acl
            tables = conn.execute(
                text(
                    "SELECT c.oid::regclass::text AS name, c.relkind FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'S', 'v', 'm')"
                )
            ).all()
            assert any(t.name == "documents" for t in tables)
            for t in tables:
                privs = (
                    ("USAGE", "SELECT", "UPDATE")
                    if t.relkind == "S"
                    else ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES")
                )
                fn = "has_sequence_privilege" if t.relkind == "S" else "has_table_privilege"
                for p in privs:
                    granted = conn.execute(
                        text(f"SELECT {fn}(:r, :t, :p)"), {"r": role, "t": t.name, "p": p}
                    ).scalar_one()
                    assert not granted, (role, t.name, p)
            # Funciones propias del esquema (no las de extensiones como pgvector).
            functions = (
                conn.execute(
                    text(
                        "SELECT p.oid::regprocedure::text FROM pg_proc p "
                        "JOIN pg_namespace n ON n.oid = p.pronamespace "
                        "WHERE n.nspname = 'public' AND NOT EXISTS ("
                        "  SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_proc'::regclass "
                        "  AND d.objid = p.oid AND d.deptype = 'e')"
                    )
                )
                .scalars()
                .all()
            )
            assert "llm_spend_usd_since(timestamp with time zone)" in functions
            for f in functions:
                assert not conn.execute(
                    text("SELECT has_function_privilege(:r, :f, 'EXECUTE')"), {"r": role, "f": f}
                ).scalar_one(), (role, f)
    engine.dispose()


@pytest.mark.parametrize("role", API_ROLES)
def test_api_role_cannot_read(supabase_sim: dict[str, str], role: str) -> None:
    engine = create_engine(supabase_sim["superuser"])
    with engine.connect() as conn:
        conn.execute(text(f"SET ROLE {role}"))
        with pytest.raises(ProgrammingError, match="permission denied"):
            conn.execute(text("SELECT count(*) FROM public.documents"))
    engine.dispose()


def test_app_role_works_under_rls(supabase_sim: dict[str, str]) -> None:
    engine = create_engine(supabase_sim["app"])
    org = uuid.uuid4()
    with engine.begin() as conn:
        assert conn.execute(text("SELECT current_user")).scalar_one() == "contable_app"
        conn.execute(text("SELECT set_config('app.organization_id', :o, true)"), {"o": str(org)})
        conn.execute(
            text("INSERT INTO organizations (id, name) VALUES (:o, 'sim')"), {"o": str(org)}
        )
        assert conn.execute(text("SELECT count(*) FROM organizations")).scalar_one() == 1
        assert (
            conn.execute(text("SELECT llm_spend_usd_since(now() - interval '1 day')")).scalar_one()
            == 0
        )
    with engine.connect() as conn:
        # Sin contexto de organización no se ve nada.
        assert conn.execute(text("SELECT count(*) FROM organizations")).scalar_one() == 0
    engine.dispose()
