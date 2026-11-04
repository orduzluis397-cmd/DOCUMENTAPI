-- =============================================================================================
-- Contable IA · preparación de la base en Supabase (CR-005). Idempotente: se puede repetir.
--
-- Se corre con el rol `postgres` de Supabase (SQL Editor del panel o psql con
-- DATABASE_URL_MIGRATIONS), ANTES de la primera migración y, por seguridad, otra vez DESPUÉS
-- de cada `alembic upgrade head` (deploy.yml lo hace solo). En Supabase no corren los scripts de
-- infra/postgres/initdb; este archivo hace lo mismo y además cierra la API pública:
--
--   1. Extensiones vector (pgvector) y unaccent.
--   2. Rol de la app `contable_app`: LOGIN, sin superusuario, sin BYPASSRLS, sin CREATEROLE.
--      SIN contraseña aquí (nada de secretos en el repositorio). Después se le pone con
--      `\password contable_app` en psql (recomendado: viaja cifrada) o con
--      `ALTER ROLE contable_app WITH PASSWORD '...'` en el SQL Editor.
--   3. Los mismos GRANT y DEFAULT PRIVILEGES que 02-roles.sh: solo DML sobre lo que cree el rol
--      que migra (`postgres`), nunca DDL.
--   4. Revoca TODO a `anon` y `authenticated` (los roles de la Data API/PostgREST de Supabase)
--      sobre el esquema public: tablas, secuencias, funciones, uso del esquema y privilegios
--      por defecto. Las funciones nuevas tampoco quedan ejecutables por PUBLIC.
--
-- Defensa en profundidad: además, en el panel de Supabase se APAGA la Data API (ver la guía,
-- docs/deploy/GUIA-DESPLIEGUE.md). Aun si alguien la reactiva, estos roles no ven nada y todas
-- las tablas tienen RLS forzado.
-- =============================================================================================

-- 1. Extensiones (en Supabase quedan en el esquema `extensions`).
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'extensions') THEN
    EXECUTE 'CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions';
    EXECUTE 'CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA extensions';
  ELSE
    EXECUTE 'CREATE EXTENSION IF NOT EXISTS vector';
    EXECUTE 'CREATE EXTENSION IF NOT EXISTS unaccent';
  END IF;
END
$$;

-- 2. Rol de la aplicación.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'contable_app') THEN
    CREATE ROLE contable_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
  -- Si ya existía, se comprueba que siga siendo seguro (un no superusuario no puede cambiar
  -- SUPERUSER/BYPASSRLS de otro rol, así que se detiene en vez de corregirlo).
  IF EXISTS (
    SELECT 1 FROM pg_roles
    WHERE rolname = 'contable_app' AND (rolsuper OR rolbypassrls OR rolcreaterole OR NOT rolcanlogin)
  ) THEN
    RAISE EXCEPTION 'contable_app existe con atributos inseguros (SUPERUSER/BYPASSRLS/CREATEROLE) o sin LOGIN';
  END IF;
  -- Sin pertenencia a otros roles: no hereda nada de anon/authenticated/postgres.
  IF EXISTS (
    SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
    WHERE r.rolname = 'contable_app'
  ) THEN
    RAISE EXCEPTION 'contable_app es miembro de otro rol; revisa con \du contable_app';
  END IF;
END
$$;

-- 3. Permisos del rol de la app (mismos que infra/postgres/initdb/02-roles.sh).
DO $$
BEGIN
  EXECUTE format('GRANT CONNECT, TEMPORARY ON DATABASE %I TO contable_app', current_database());
END
$$;
GRANT USAGE ON SCHEMA public TO contable_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO contable_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO contable_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO contable_app;
-- Funciones nuevas: no ejecutables por PUBLIC (cada migración da EXECUTE a quien lo necesite).
ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

-- 4. Cerrar la API pública de Supabase sobre public.
DO $$
DECLARE
  r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', r);
      EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', r);
      EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM %I', r);
      EXECUTE format('REVOKE ALL ON SCHEMA public FROM %I', r);
      -- Objetos que cree después el rol que corre esto (el que migra).
      EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM %I', r);
      EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I', r);
      EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM %I', r);
      EXECUTE format('ALTER DEFAULT PRIVILEGES REVOKE ALL ON FUNCTIONS FROM %I', r);
    END IF;
  END LOOP;
END
$$;

-- Funciones propias ya creadas en public (no las de extensiones): fuera de PUBLIC. Las que use
-- la app conservan su GRANT explícito (p. ej. llm_spend_usd_since, migración 0002).
DO $$
DECLARE
  f regprocedure;
BEGIN
  FOR f IN
    SELECT p.oid::regprocedure
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public'
      AND pg_has_role(p.proowner, 'USAGE')
      AND NOT EXISTS (
        SELECT 1 FROM pg_depend d
        WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid AND d.deptype = 'e'
      )
  LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC', f);
  END LOOP;
END
$$;
-- La app no toca la tabla de versiones de Alembic.
DO $$
BEGIN
  IF to_regclass('public.alembic_version') IS NOT NULL THEN
    REVOKE ALL ON public.alembic_version FROM contable_app;
  END IF;
END
$$;

-- Comprobación rápida (debe devolver 0 filas): privilegios de anon/authenticated en public.
SELECT grantee, table_name, privilege_type
FROM information_schema.role_table_grants
WHERE table_schema = 'public' AND grantee IN ('anon', 'authenticated');
