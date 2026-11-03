# Contable IA

[English](README.md) · **Español**

> **En construcción.** El entorno de desarrollo está listo; todavía no hay funcionalidades del
> producto, resultados ni cifras. Este README se completará en el lanzamiento (fase 5).

Contable IA es una aplicación web de Document AI contable en español para pymes colombianas. Recibe
los documentos contables de una empresa (facturas electrónicas DIAN, RUT, cuentas de cobro,
contratos y extractos bancarios), extrae y valida sus datos, detecta anomalías, responde preguntas
tributarias con citas y concilia facturas contra extractos **con aprobación humana**.

Integra una **capa de calidad y gobernanza** (evals, trazas, jueces alineados, políticas, auditoría,
costo) que se construye en la fase 1 y crece en cada fase posterior.

## Caso de uso guía

Todo se diseña y se prueba contra un mismo caso. Laura, contadora independiente, lleva 8 pymes. Una
de ellas, una ferretería, tiene unas 130 compras al mes y hoy el cierre le toma 2 días. El flujo
previsto:

1. Carga del mes en lote (ZIP de factura electrónica, fotos de cuentas de cobro, un RUT nuevo,
   extracto bancario).
2. Extracción en cascada: XML → parser determinista; texto libre → modelo propio; falla → API
   grande; falla → humano.
3. Validación: DV del NIT, totales, perfil tributario del proveedor nuevo.
4. Alertas: duplicados y montos atípicos con explicación SHAP.
5. Revisión humana: corrección de campos y descarte de falsas alarmas, todo auditado.
6. Consulta normativa con RAG, con citas (o abstención).
7. Conciliación de facturas contra movimientos (exactos, difusos, agrupados, 4 por mil, comisiones).
8. Aprobación según política: en bloque, individual o doble según confianza y monto.
9. Registro, auditoría, informe del cierre y exportación al software contable.
10. Calidad en segundo plano: trazas, costo del cierre, rutina semanal de correcciones.

**Meta:** que el cierre de 2 días baje a medio día, con cada número verificable.

## Arquitectura y stack

| Capa | Componentes | Herramientas |
|------|-------------|--------------|
| Interfaz | Aplicación web; cliente MCP externo | Next.js (App Router, TypeScript, Tailwind, shadcn/ui), Clerk o Auth.js |
| Servicio | API; workers; servidor MCP | FastAPI, Pydantic v2, Celery + Redis, SDK oficial MCP (FastMCP) |
| Núcleo | Extracción; ML clásico; RAG; agente | lxml, Docling/PyMuPDF, Tesseract (`spa`), Instructor; scikit-learn, LightGBM, SHAP; pgvector + FTS + re-ranker; LangGraph |
| Modelos | Enrutador en cascada | Parser → modelo propio (vLLM) → API grande → humano |
| Datos | Relacional, vectores, auditoría, checkpoints, archivos, experimentos | PostgreSQL 16/17 + pgvector, R2/S3 (MinIO en local), MLflow |
| Calidad (transversal) | Trazas, evals, jueces, políticas, auditoría, costo | Langfuse (o Arize Phoenix), DeepEval + pytest, GitHub Actions |
| Despliegue | | Vercel (web), Cloud Run o Fly.io (API, worker), Neon o Supabase (Postgres), R2/S3 |

Estructura del monorepo: `apps/api` (FastAPI con uv), `apps/web` (Next.js), `services/mcp-server`,
`ml/`, `evals/`, `infra/`, `docs/`. Decisión clave:
[ADR 0001 · Monorepo y PostgreSQL como única base](docs/adr/0001-monorepo-y-postgres-unica-base.md).

## Estado

- [x] Preparación: monorepo, servicios locales (Docker Compose), esqueletos de backend y frontend,
      pre-commit, CI base, `.env.example`, ADR 0001
- [ ] Fase 0 · Datos y línea base (corpus anonimizado, conjunto dorado, extractor v0)
- [ ] Fase 1 · Evals primero (trazas, taxonomía de errores, jueces alineados, puerta de CI)
- [ ] Fase 2 · RAG híbrido y ML clásico (consultas tributarias, duplicados y anomalías)
- [ ] Fase 3 · Agente gobernado y servidor MCP (conciliación con aprobación humana)
- [ ] Fase 4 · Costo y modelo propio (ajuste fino, vLLM, enrutador)
- [ ] Fase 5 · Usuarios reales y lanzamiento

## Cómo correrlo en local

Requisitos: Docker (Compose v2), [uv](https://docs.astral.sh/uv/), Python 3.12, Node LTS y pnpm.

```bash
# 1. Configuración (.env nunca se sube)
cp .env.example .env

# 2. Servicios locales: Postgres + pgvector, Redis, MinIO (con el bucket inicial)
docker compose -f infra/docker-compose.yml up -d
#    Phoenix opcional para trazas:
#    docker compose -f infra/docker-compose.yml --profile observability up -d

# 3. API (http://localhost:8000/health)
cd apps/api && uv run uvicorn app.main:app --reload

# 4. Worker
cd apps/api && uv run celery -A app.workers worker -l info

# 5. Web
cd apps/web && pnpm install && pnpm dev

# 6. Migraciones
cd apps/api && uv run alembic upgrade head
```

Pruebas y calidad de código:

```bash
cd apps/api && uv run pytest
cd apps/web && pnpm lint
uv run --directory apps/api pre-commit install          # hooks de git: Ruff, mypy, Prettier, ESLint, gitleaks
uv run --directory apps/api pre-commit run --all-files
```

## Privacidad

Contable IA maneja datos personales y tributarios protegidos por la Ley 1581 de 2012 y el Decreto
1377 de 2013. Para desarrollo, evals y cualquier API externa solo se usan documentos
**anonimizados**. Los documentos crudos viven en `data/`, que está en `.gitignore` y **nunca** se
sube al repositorio; gitleaks corre en pre-commit y en CI para bloquear secretos.

## Licencia

[MIT](LICENSE) © 2026 orduzluis397-cmd
