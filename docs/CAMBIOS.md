# Registro de solicitudes de cambio

> Lo mantiene el orquestador. Cada pedido del usuario que altere alcance, diseño, prioridades o
> código se registra aquí antes de actuar.
>
> Estados: registrado → en análisis → esperando aprobación → aprobado → en curso →
> en verificación → hecho (o rechazado / pospuesto).
> Tipos: menor · mayor · crítico (ver ORQUESTADOR.md §2.2).

## Resumen

| ID | Fecha | Título | Tipo | Estado |
|----|-------|--------|------|--------|
| CR-001 | 2026-11-03 | Repo privado durante el desarrollo | menor | rechazado (reemplazado por CR-002) |
| CR-002 | 2026-11-03 | Repo público desde ya | menor | hecho |
| CR-003 | 2026-11-03 | pypdfium2 en lugar de PyMuPDF en la API | mayor | hecho (API) · pendiente decisión anonimizador |

---

### CR-001 · Repo privado durante el desarrollo

- **Fecha:** 2026-11-03
- **Pedido del usuario:** "me sirve así" (repo `orduzluis397-cmd/DOCUMENTAPI` privado; §7.1 pedía público)
- **Interpretación:** el repo queda privado durante las fases 0–4; se hace público en la Fase 5, antes del lanzamiento.
- **Tipo:** menor
- **Fases y agentes afectados:** Preparación; `lanzamiento-usuarios` (Fase 5: hacer público el repo y revisar el historial con gitleaks antes).
- **Archivos o módulos:** ninguno
- **Evals afectadas / nuevas:** ninguna
- **Costo, calendario y riesgo:** los minutos de GitHub Actions en repos privados tienen cupo mensual gratuito limitado; vigilar el consumo de `evals.yml`.
- **Reglas duras involucradas:** ninguna
- **Plan:** 1. Registrar. 2. Añadir a la Fase 5 la tarea "hacer público el repo".
- **Aprobación del usuario:** aprobada el 2026-11-03
- **Estado:** rechazado (el usuario cambió de opinión; ver CR-002)
- **Verificación:** —
- **Commits / PR:** —

---

### CR-002 · Repo público desde ya

- **Fecha:** 2026-11-03
- **Pedido del usuario:** "vuelve público el repo"
- **Interpretación:** `orduzluis397-cmd/DOCUMENTAPI` pasa a público ahora, como pide §7.1.
- **Tipo:** menor (el repo estaba vacío: no se expuso nada)
- **Fases y agentes afectados:** todos; cada push queda visible al instante.
- **Archivos o módulos:** ninguno
- **Evals afectadas / nuevas:** ninguna
- **Costo, calendario y riesgo:** Actions gratis sin cupo en repos públicos. Riesgo: cualquier secreto o dato sin anonimizar que entre en un commit queda público → gitleaks en pre-commit y en CI, y revisión del orquestador antes de cada push.
- **Reglas duras involucradas:** 1 (datos personales)
- **Plan:** 1. `gh repo edit --visibility public`. 2. Revisar con gitleaks antes del primer push.
- **Aprobación del usuario:** pedido explícito el 2026-11-03
- **Estado:** hecho
- **Verificación:** `gh repo view` → visibility PUBLIC, repo vacío
- **Commits / PR:** —

---

### CR-003 · pypdfium2 en lugar de PyMuPDF en la API

- **Fecha:** 2026-11-03
- **Pedido del usuario:** "vamos con la opción recomendada" (A: `pypdfium2`)
- **Interpretación:** la API (repo MIT, servida en red) no depende de PyMuPDF (AGPL-3.0). Lectura de texto de PDF con `pypdfium2` (Apache-2.0/BSD-3) o Docling (MIT).
- **Tipo:** mayor (cambio de dependencia del núcleo)
- **Fases y agentes afectados:** F0 (`extraccion-app`, `datos-corpus` por la redacción de PDF en `ml/anonymize.py`).
- **Archivos o módulos:** `apps/api/pyproject.toml`, `uv.lock`, INSTRUCCIONES.md §3/§7.2/§8.3, `.claude/agents/extraccion-app.md`, README.md, README.es.md, adenda en ADR 0001.
- **Evals afectadas / nuevas:** ninguna aún (no hay extractor).
- **Costo, calendario y riesgo:** sin costo. Riesgo: `pypdfium2` no hace redacción real (borrar texto del PDF), que §8.1 pide para anonimizar → decisión pendiente para `ml/anonymize.py`.
- **Reglas duras involucradas:** 1 (la anonimización de PDF debe seguir siendo segura).
- **Plan:** 1. Cambiar dependencia ✔. 2. Actualizar documentación y ADR ✔. 3. Usuario decide herramienta de redacción del anonimizador.
- **Aprobación del usuario:** aprobada el 2026-11-03
- **Estado:** hecho (API) · pendiente decisión del anonimizador
- **Verificación:** `uv run pytest` 1 passed; `mypy app` sin errores; `uv.lock` sin pymupdf.
- **Commits / PR:** ver `git log` (CR-003)

---

## Plantilla

### CR-000 · <título corto>

- **Fecha:** AAAA-MM-DD
- **Pedido del usuario:** "<en sus palabras>"
- **Interpretación:** <qué se va a hacer>
- **Tipo:** menor | mayor | crítico
- **Fases y agentes afectados:** <…>
- **Archivos o módulos:** <…>
- **Evals afectadas / nuevas:** <…>
- **Costo, calendario y riesgo:** <…>
- **Reglas duras involucradas:** <ninguna | cuáles>
- **Plan:** 1. … 2. …
- **Aprobación del usuario:** <no requerida | pendiente | aprobada el AAAA-MM-DD>
- **Estado:** registrado
- **Verificación:** <pruebas/evals corridas y resultado>
- **Commits / PR:** <…>
