#!/usr/bin/env bash
# Roles y bases de Contable IA. Se ejecuta solo al crear el volumen por primera vez.
#
# - POSTGRES_USER (contable): dueño del esquema; lo usan las migraciones (Alembic).
# - contable_app: rol de la aplicación. LOGIN, sin superusuario y sin BYPASSRLS, para que
#   Row Level Security aplique siempre (CLAUDE.md, regla 6). Solo DML sobre las tablas que
#   cree el rol de migraciones; nunca DDL.
# - contable_ia_test: base para pruebas, con las mismas extensiones (heredadas de template1).
#
# Las contraseñas son solo para desarrollo local (ver .env.example).
set -eo pipefail

APP_USER="${POSTGRES_APP_USER:-contable_app}"
APP_PASSWORD="${POSTGRES_APP_PASSWORD:-contable_app_local}"
TEST_DB="${POSTGRES_TEST_DB:-contable_ia_test}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_user="$APP_USER" -v app_password="$APP_PASSWORD" -v test_db="$TEST_DB" \
  -v owner="$POSTGRES_USER" <<'SQL'
CREATE ROLE :"app_user" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS
  PASSWORD :'app_password';
CREATE DATABASE :"test_db" OWNER :"owner";
SQL

for db in "$POSTGRES_DB" "$TEST_DB"; do
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" \
    -v app_user="$APP_USER" -v owner="$POSTGRES_USER" -v db="$db" <<'SQL'
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE :"db" TO :"app_user";
GRANT USAGE ON SCHEMA public TO :"app_user";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_user";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO :"app_user";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO :"app_user";
SQL
done

echo "rol $APP_USER y base $TEST_DB listos"
