# contable-ia-api

API de Contable IA (FastAPI + Pydantic v2 + SQLAlchemy 2 + Celery). Gestionada con `uv` (Python 3.12).

```bash
docker compose -f ../../infra/docker-compose.yml up -d   # postgres, redis, minio
uv sync
uv run alembic upgrade head          # migra con DATABASE_URL_MIGRATIONS (rol dueño `contable`)
uv run python -m app.db.seed         # organización y usuario demo (solo local)
uv run uvicorn app.main:app --reload # la app usa DATABASE_URL (rol `contable_app`, sin BYPASSRLS)
uv run celery -A app.workers worker -l info   # en Windows: añade -P solo
uv run pytest                        # contra contable_ia_test (se omiten si no hay Postgres)
uv run ruff check . && uv run ruff format --check .
uv run mypy app tests
```

## Base de datos

- Tablas: `organizations`, `users`, `documents`, `extractions`, `extracted_fields`, `llm_calls`,
  `audit_events` (`app/db/models.py`, migración `alembic/versions/*_0001_*`).
- **RLS activo y forzado** en todas: política `organization_id = current_setting('app.organization_id')`.
  `app/db/session.py` fija ese valor con `set_config(..., true)` al inicio de cada transacción de
  una sesión de inquilino; sin él, el rol de la app no ve ninguna fila.
- `audit_events`: el rol de la app solo tiene `SELECT`/`INSERT`; un trigger rechaza `UPDATE` y
  `DELETE` para cualquier rol. Se escribe en la misma transacción que el cambio
  (`app/governance/audit.py`).

## Endpoints

| Método | Ruta | Qué hace |
|--------|------|----------|
| `POST` | `/documents` | Carga múltiple (`files`): valida tipo real y tamaño, sube a MinIO/R2, crea filas y encola `documents.process` |
| `GET` | `/documents` | Lista de la organización con estado |
| `GET` | `/documents/{id}` | Detalle con la última extracción y sus campos |
| `GET` | `/documents/{id}/file` | Archivo original |
| `PATCH` | `/fields/{id}` | Corrección humana → `corrected_value` + `audit_events` (misma transacción) |

## Autenticación (pendiente)

`app/auth.py` es un **stub de desarrollo**: en `APP_ENV=local|test` toma el usuario y la
organización de las cabeceras `X-User-Id` y `X-Organization-Id`; en otros entornos responde 501.
Se reemplaza por Clerk/Auth.js en ese módulo sin tocar los routers.

## Worker

`documents.process` (`app/workers/tasks.py`) es un stub que pasa el documento a `processing`.
El enrutador de extracción (F0-09) se conecta ahí.
