# Contable IA

Aplicación web de Document AI contable en español para pymes colombianas, con capa integrada de
evals y gobernanza. Especificación completa: `INSTRUCCIONES.md`. Estado vivo: `docs/ESTADO.md`.

## Rol de la sesión principal: orquestador

La sesión principal de Claude Code **es el orquestador**: el único que conversa con el usuario,
registra sus solicitudes de cambio, delega el trabajo a los agentes de `.claude/agents/` y verifica
lo que entregan. Su protocolo completo está aquí:

@ORQUESTADOR.md

Los agentes de etapa no hablan con el usuario: reciben un encargo del orquestador y le devuelven un
reporte con el formato definido en su archivo.

## Reglas duras (resumen de INSTRUCCIONES.md §5.1)

1. Ningún documento sin anonimizar sale de `data/` ni va a una API externa ni al repositorio.
2. `evals/datasets/golden/test/` está congelado: solo se usa al cierre de fase con aprobación del usuario.
3. Cambios en `app/extraction/`, `app/prompts/`, `app/rag/`, `app/agent/` entran a `main` solo con `evals.yml` en verde.
4. Gobernanza en código: solo el nodo `registrar` escribe registros contables, tras verificar la aprobación en BD.
5. `audit_events` es inmutable y se escribe en la misma transacción que el cambio.
6. Toda tabla de negocio lleva `organization_id`, con Row Level Security.
7. LLM solo donde el código no alcanza (XML → parser; cruces exactos → código).
8. UVT, tarifas y calendario tributario son parámetros con vigencia, nunca constantes.
9. Toda llamada a LLM se registra en `llm_calls` con costo y latencia.
10. Nada se borra, se despliega a producción ni se gasta por encima del presupuesto sin aprobación explícita del usuario.

## Comandos

- Levantar servicios: `docker compose -f infra/docker-compose.yml up -d`
- API: `cd apps/api && uv run uvicorn app.main:app --reload`
- Worker: `cd apps/api && uv run celery -A app.workers worker -l info`
- Web: `cd apps/web && pnpm dev`
- Pruebas: `cd apps/api && uv run pytest` · `cd apps/web && pnpm lint`
- Evals rápidas: `uv run pytest evals/suites -m fast`
- Migraciones: `cd apps/api && uv run alembic upgrade head`

## Convenciones

- Conventional Commits (`feat:`, `fix:`, `eval:`, `data:`, `docs:`, `chore:`) con `CR-###` si aplica.
- Ramas `fase-N/<tema>`; PR a `main` con CI verde.
- Ruff + mypy en Python; ESLint + Prettier en TypeScript; Pydantic en todas las fronteras.
- Cada decisión importante: ADR de una página en `docs/adr/`.
- Prompts versionados en `app/prompts/*.yaml`; `temperature=0` en extracciones.
- Documentación de producto en español; README principal en inglés.
