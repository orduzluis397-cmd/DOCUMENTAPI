# Estado del proyecto

> Lo mantiene el orquestador. Se actualiza al final de cada paso y de cada sesión.

**Última actualización:** 2026-11-03
**Fase actual:** Preparación · semana 0 de 22

## Criterios de salida de la fase actual

- [ ] `docker compose up` levanta postgres, redis y minio
- [ ] `uv run pytest` y `pnpm lint` en verde
- [ ] `ci.yml` corre en cada push
- [ ] ADR 0001 escrito
- [ ] Política de tratamiento de datos y formato de autorización listos

## Cifras clave

| Métrica | Línea base | Actual | Fecha |
|---------|-----------|--------|-------|
| Precisión por campo (val) | — | — | — |
| Docs 100 % correctos | — | — | — |
| Costo por documento (USD) | — | — | — |
| Latencia p95 (s) | — | — | — |
| Gasto API del mes (USD) | — | — | — |

## Fases

| Fase | Estado | Cerrada el |
|------|--------|-----------|
| Preparación | en curso | — |
| 0 · Datos y línea base | pendiente | — |
| 1 · Evals primero | pendiente | — |
| 2 · RAG y ML clásico | pendiente | — |
| 3 · Agente gobernado y MCP | pendiente | — |
| 4 · Costo y modelo propio | pendiente | — |
| 5 · Usuarios y lanzamiento | pendiente | — |

## Bloqueos y pendientes del usuario

- Instalar WSL2 (`wsl --install` como administrador + reinicio) para que Docker Desktop arranque.
- `gh auth login` y confirmar que el repo `orduzluis397-cmd/DOCUMENTAPI` existe (hoy responde "not found": privado o no creado).
- Copiar `.env.example` a `.env` y poner las claves (nunca en el chat ni en el repo).

## Hecho en Preparación

- 2026-11-03: instalados uv 0.13.7, pnpm 12.16.1, gh 2.103.3, Docker Desktop 4.98 (sin WSL2 aún).
- 2026-11-03: `git init -b main`, remoto `origin` → github.com/orduzluis397-cmd/DOCUMENTAPI.

## Hallazgos para la Fase 0 (del glosario, experto-contable, 2026-11-03)

- `datos-corpus`: definir en GUIA.md si `total` = valor facturado o neto a pagar (en el XML las retenciones van en `WithholdingTaxTotal` y quizá no se restan de `PayableAmount`); ajustar el validador de totales.
- `datos-corpus`: responsabilidades de la casilla 53 como catálogo con vigencia (la 09 fue retirada de oficio), no `Enum` cerrado.
- `datos-corpus`: ampliar la regex de NIT del anonimizador a NIT de persona natural (longitud variable) y probarla — regla dura 1.
- Contador asesor: 11 puntos pendientes al final de `docs/glosario.md`.

## Próximo paso

- Agente `preparacion-entorno` ejecutando §7 pasos 2–9 (sin push ni Docker hasta resolver bloqueos).
