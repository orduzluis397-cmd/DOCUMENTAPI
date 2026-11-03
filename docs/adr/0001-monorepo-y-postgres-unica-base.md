# ADR 0001 · Monorepo FastAPI + Next.js y PostgreSQL como única base de datos

- **Estado:** aceptado
- **Fecha:** 2026-11-03
- **Etapa:** Preparación (INSTRUCCIONES.md §7, paso 7)

## Contexto

Contable IA tiene una API en Python (FastAPI, workers Celery, extracción, RAG, agente LangGraph,
servidor MCP), una interfaz web en TypeScript (Next.js) y una capa transversal de evals y gobernanza
que debe ver a la vez código, prompts, datos de evaluación y CI. Lo construye una sola persona con
agentes, a 15–20 h/semana, con presupuesto de hosting de US$0–25/mes.

Los datos necesitan: modelo relacional multiempresa con Row Level Security (`organization_id`),
búsqueda vectorial y de texto completo en español para el RAG, auditoría inmutable escrita en la
**misma transacción** que el cambio (regla dura 5) y checkpoints del agente (`PostgresSaver`).

## Opciones

1. **Monorepo + PostgreSQL único** (pgvector + FTS `spanish`/`unaccent` + tablas de auditoría).
2. **Repos separados** (api, web, evals) + PostgreSQL.
3. **Monorepo + base vectorial dedicada** (Qdrant, Pinecone o similar) junto a PostgreSQL.

## Decisión

Opción 1.

- Un solo repositorio con `apps/api` (uv, Python 3.12), `apps/web` (pnpm, Next.js),
  `services/mcp-server`, `ml/`, `evals/`, `infra/` y `docs/`. Una sola CI (`ci.yml`) y una sola
  puerta de evals (`evals.yml`) que ven todos los cambios a la vez.
- PostgreSQL 16/17 con `pgvector` es la **única** base: relacional, vectores (HNSW), texto completo
  (`tsvector` + GIN), auditoría (`audit_events` sin `UPDATE`/`DELETE`), `llm_calls` y checkpoints
  del agente. Las extensiones `vector` y `unaccent` se crean al iniciar el contenedor local.
- Archivos en almacenamiento de objetos (MinIO en local, R2/S3 en la nube); colas en Redis.

## Consecuencias

**A favor**

- Un PR puede cambiar extractor, prompt, esquema y eval juntos, y la puerta de evals lo juzga
  completo. Menos coordinación de versiones entre repos.
- Auditoría y cambio de negocio en la misma transacción; RLS y filtro por `organization_id`
  también en los fragmentos privados del RAG, sin sincronizar dos bases.
- Un solo servicio de datos que operar, respaldar (PITR) y pagar (Neon/Supabase con capa gratuita).

**En contra / riesgos**

- pgvector con HNSW rinde menos que una base vectorial dedicada a gran escala; aceptable para el
  volumen esperado (miles a decenas de miles de fragmentos). Se revisa en la fase 2 con la tabla de
  recuperación (ADR 0004) si la p95 no cumple.
- La CI del monorepo crece: se mitiga con filtros por ruta en los workflows y cachés de uv/pnpm.
- Dos gestores de paquetes (uv y pnpm) conviven en el mismo repo; los hooks de pre-commit los
  requieren a ambos en el PATH.

## Adenda 2026-11-03 · Licencias de dependencias (CR-003)

El repositorio es MIT y la API se servirá en red. PyMuPDF es AGPL-3.0, cuya cláusula de red
obligaría a licenciar la API como AGPL. **Decisión:** la API no depende de PyMuPDF; el texto de
PDF se lee con `pypdfium2` (Apache-2.0/BSD-3) o Docling (MIT). Toda dependencia nueva de `apps/`
debe tener licencia compatible con MIT; las copyleft fuertes (GPL/AGPL) requieren ADR.
