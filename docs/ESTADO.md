# Estado del proyecto

> Lo mantiene el orquestador. Se actualiza al final de cada paso y de cada sesión.

**Última actualización:** 2026-11-03
**Fase actual:** 0 · Datos y línea base · semana 1 de 22

## Criterios de salida de la Preparación (cerrada 2026-11-03)

- [x] `docker compose up` levanta postgres, redis y minio (verificado 2026-11-03)
- [x] `uv run pytest` y `pnpm lint` en verde
- [x] `ci.yml` corre en cada push — run 41704806661 verde (4 jobs)
- [x] ADR 0001 escrito
- [~] Política de tratamiento de datos y formato de autorización: borradores en `docs/legal/`; falta llenar placeholders y revisión de abogado

## Criterios de salida de la Fase 0

- [ ] URL pública con login
- [ ] 250 documentos anonimizados y anotados
- [ ] Conjunto de prueba congelado
- [ ] Informe de línea base (precisión por campo, docs 100 %, costo/doc, p50/p95)
- [ ] ADR 0002 (parser determinista para XML; LLM solo para formatos libres)

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
| Preparación | cerrada | 2026-11-03 |
| 0 · Datos y línea base | en curso | — |
| 1 · Evals primero | pendiente | — |
| 2 · RAG y ML clásico | pendiente | — |
| 3 · Agente gobernado y MCP | pendiente | — |
| 4 · Costo y modelo propio | pendiente | — |
| 5 · Usuarios y lanzamiento | pendiente | — |

## Bloqueos y pendientes del usuario

- Decidir licencia del lector de PDF: PyMuPDF (AGPL) vs `pypdfium2` (Apache/BSD).
- Llenar placeholders de `docs/legal/` y hacerlos revisar por un abogado.
- Configurar tope de gasto mensual en cada proveedor.
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

- Usuario: recolectar documentos (meta 100 al final de la semana 1).
- En paralelo (ramas `fase-0/*`): `datos-corpus` → anonimizador, esquemas, validadores, GUIA.md; `extraccion-app` → BD con RLS, API, worker y web.
