# Contable IA — Instrucciones de desarrollo

> Especificación ejecutable del proyecto. La leen el orquestador y los agentes de cada etapa.
> Cada agente lee **solo** las secciones que su archivo de agente le indica.
> Versión 1.0 · 2026-11-03

---

## 0. Índice

1. Producto y objetivo
2. Caso de uso guía
3. Arquitectura y stack
4. Estructura del repositorio
5. Convenciones y reglas no negociables
6. Conocimiento del dominio
7. Preparación
8. Fase 0 · Datos y línea base (semanas 1–3)
9. Fase 1 · Evals primero (semanas 4–6)
10. Fase 2 · RAG híbrido y ML clásico (semanas 7–10)
11. Fase 3 · Agente gobernado y servidor MCP (semanas 11–14)
12. Fase 4 · Costo y modelo propio (semanas 15–18)
13. Fase 5 · Usuarios reales y lanzamiento (semanas 19–22)
14. Riesgos y plan B
15. Lista final del portafolio
16. Mapa de agentes

---

## 1. Producto y objetivo

**Contable IA** es una aplicación web que recibe los documentos contables de una pyme colombiana
(facturas electrónicas DIAN, RUT, cuentas de cobro, contratos y extractos bancarios), extrae sus
datos, los valida, detecta anomalías, responde preguntas tributarias con citas y concilia facturas
contra extractos **con aprobación humana**.

El proyecto integra una **capa de calidad y gobernanza** (evals, trazas, jueces alineados, políticas,
auditoría, costo) que se construye en la fase 1 y crece en cada fase posterior.

Objetivo profesional: demostrar AI Engineering y ML Engineering de nivel senior: extracción, RAG,
agentes con aprobación humana, ML clásico, un modelo pequeño propio, evals, observabilidad,
gobernanza y control de costos, con usuarios reales.

Calendario: 22 semanas a 15–20 h/semana. Si hay menos tiempo, se estiran las semanas; **el orden de
las fases no cambia** (evals antes que RAG y agente).

---

## 2. Caso de uso guía

Todo se diseña y se prueba contra este caso. Los escenarios de evaluación son variantes de él.

**Contexto.** Laura, contadora independiente, lleva 8 pymes. Una es Ferretería El Tornillo S.A.S.,
responsable de IVA y agente de retención, con ~130 compras al mes. Hoy el cierre le toma 2 días.

| # | Paso | Fase que lo construye | Cómo se mide |
|---|------|----------------------|--------------|
| 1 | Carga de 140 archivos: 110 ZIP de factura electrónica, 18 fotos de cuentas de cobro, 1 RUT nuevo, 10 varios, extracto bancario | 0 | Documentos aceptados sin error |
| 2 | Extracción en cascada: XML → parser; libre → modelo propio; falla → API grande; falla → humano | 0 y 4 | Precisión por campo; % por nivel; costo/doc |
| 3 | Validación: DV del NIT, totales, perfil tributario del proveedor nuevo | 0 | Tasa de validadores |
| 4 | Alertas: duplicado y monto atípico con explicación SHAP | 2 | Precisión@k; falsas alarmas |
| 5 | Revisión humana: corrige campos, descarta falsas alarmas, todo auditado | 0 y 1 | Tasa de corrección por campo |
| 6 | Consulta normativa (RAG): "¿debo generar documento soporte por las cuentas de cobro?" | 2 | Recall@5, fidelidad, citas válidas, abstención |
| 7 | Conciliación: 128 facturas vs 95 movimientos; exactos, difusos, agrupados, 4 por mil, comisiones | 3 | Precisión/recall de cruces |
| 8 | Aprobación según política: bloque si confianza alta, individual si baja, doble si supera monto | 3 | Cero registros sin aprobación |
| 9 | Registro, auditoría, informe del cierre y exportación al software contable | 3 y 5 | Importación sin errores |
| 10 | Calidad en segundo plano: trazas, costo del cierre, correcciones a la rutina semanal | 1 y 5 | Costo y duración del cierre |

**Meta:** el cierre de 2 días baja a medio día, con cada número verificable.

---

## 3. Arquitectura y stack

| Capa | Componentes | Herramientas |
|------|-------------|--------------|
| Interfaz | Aplicación web; cliente MCP externo | Next.js (App Router, TypeScript, Tailwind, shadcn/ui), Clerk o Auth.js |
| Servicio | API; workers; servidor MCP | FastAPI, Pydantic v2, Celery + Redis, SDK oficial MCP (FastMCP) |
| Núcleo | Extracción; ML clásico; RAG; agente | lxml, Docling/PyMuPDF, Tesseract (`spa`), Instructor; scikit-learn, LightGBM, SHAP; pgvector + FTS + re-ranker; LangGraph |
| Modelos | Enrutador en cascada | Parser → modelo propio (vLLM) → API grande → humano |
| Datos | Relacional, vectores, auditoría, checkpoints, archivos, experimentos | PostgreSQL 16/17 + pgvector, R2/S3 (MinIO en local), MLflow |
| Calidad (transversal) | Trazas, evals, jueces, políticas, auditoría, costo | Langfuse (o Arize Phoenix), DeepEval + pytest, GitHub Actions |
| Despliegue | | Vercel (web), Cloud Run o Fly.io (API, worker), Neon o Supabase (Postgres), R2/S3 |

Herramientas de desarrollo: Git/GitHub, Docker Compose, uv, Python 3.12, Node LTS + pnpm, Ruff,
mypy, ESLint, Prettier, pre-commit, gitleaks, Label Studio.

Presupuesto orientativo: API LLM US$10–40/mes; hosting US$0–25/mes; GPU fase 4 US$20–60 total;
dominio US$10–15/año. **Tope de gasto mensual configurado en cada proveedor desde el día 1.**

---

## 4. Estructura del repositorio

```
contable-ia/
├── CLAUDE.md                 # reglas del proyecto (se carga en cada sesión)
├── INSTRUCCIONES.md          # este archivo
├── ORQUESTADOR.md            # protocolo del orquestador (sesión principal)
├── .claude/agents/           # un agente por etapa + experto contable
├── apps/
│   ├── web/                  # Next.js
│   └── api/                  # FastAPI (uv)
│       ├── app/
│       │   ├── main.py
│       │   ├── routers/      # documents, chat, reconciliation, admin
│       │   ├── schemas/      # Pydantic: Factura, RUT, CuentaCobro, ExtractoBancario, Contrato
│       │   ├── prompts/      # *.yaml versionados
│       │   ├── extraction/   # parsers, OCR, LLM, router en cascada
│       │   ├── rag/          # chunking, embeddings, búsqueda híbrida
│       │   ├── anomalies/    # features + modelos
│       │   ├── agent/        # grafo LangGraph, herramientas
│       │   ├── governance/   # políticas, aprobaciones, auditoría
│       │   ├── observability/
│       │   ├── db/           # SQLAlchemy 2 + Alembic
│       │   └── workers/      # Celery
│       └── tests/
├── services/mcp-server/
├── ml/
│   ├── anonymize.py
│   ├── notebooks/            # exploración; nunca código de producción
│   └── training/
├── evals/
│   ├── datasets/             # golden/, retrieval.jsonl, conciliacion/ (anonimizado)
│   ├── suites/               # pytest + DeepEval por subsistema
│   ├── judges/               # prompts + alineacion.md por juez
│   ├── reports/
│   ├── taxonomy.md
│   └── CHANGELOG.md
├── data/                     # .gitignore: crudos y sin anonimizar
├── docs/
│   ├── ESTADO.md             # lo mantiene el orquestador
│   ├── CAMBIOS.md            # registro de solicitudes de cambio
│   ├── adr/                  # 0001-..., una página cada uno
│   ├── glosario.md
│   └── architecture.md
├── infra/
│   ├── docker-compose.yml    # postgres(pgvector), redis, minio, phoenix opcional
│   └── deploy/
├── .github/workflows/        # ci.yml, evals.yml, evals-nightly.yml, deploy.yml
├── .env.example
├── README.md                 # inglés
└── README.es.md
```

---

## 5. Convenciones y reglas no negociables

### 5.1 Reglas duras (ningún agente las rompe; el orquestador las hace cumplir)

1. **Datos personales (Ley 1581 de 2012, Decreto 1377 de 2013).** Ningún documento sin anonimizar
   sale de `data/` ni se envía a una API externa ni al repositorio. `gitleaks` en pre-commit.
2. **Conjunto de prueba congelado.** `evals/datasets/golden/test/` solo se usa al cierre de fase y
   con aprobación del usuario. Nadie itera mirándolo.
3. **Evals antes de complejidad.** Ningún cambio en `app/extraction/`, `app/prompts/`, `app/rag/`,
   `app/agent/` entra a `main` sin pasar `evals.yml`.
4. **Gobernanza en código, no en prompt.** La escritura de registros contables solo ocurre en el
   nodo `registrar` tras verificar en base de datos la aprobación exigida por la política.
5. **Auditoría inmutable.** `audit_events` sin permisos de `UPDATE`/`DELETE`; se escribe en la misma
   transacción que el cambio.
6. **Multiempresa.** Toda tabla de negocio lleva `organization_id`; Row Level Security activo.
7. **LLM solo donde el código no alcanza.** XML de factura → parser determinista. Emparejamientos
   exactos → código.
8. **Parámetros con vigencia.** UVT, bases y tarifas de retención, calendario tributario: tablas con
   `vigente_desde`/`vigente_hasta`; nunca constantes en código.
9. **Costo registrado.** Toda llamada a un LLM escribe en `llm_calls` (modelo, tokens, costo USD,
   latencia ms, `trace_id`, `document_id`).
10. **Nada se borra ni se despliega a producción sin aprobación explícita del usuario.**

### 5.2 Convenciones

- Idioma: código y nombres técnicos en inglés o español consistente por módulo; documentación de
  producto en español; README principal en inglés.
- Commits: Conventional Commits (`feat:`, `fix:`, `eval:`, `data:`, `docs:`, `chore:`), uno por
  cambio lógico; referencia al cambio `CR-###` cuando aplique.
- Ramas: `fase-N/<tema>`; PR a `main` con CI verde.
- Python: Ruff + mypy estricto en `app/`; pytest; tipos Pydantic en todas las fronteras.
- TypeScript: estricto; ESLint + Prettier.
- Cada decisión importante → ADR de una página en `docs/adr/NNNN-titulo.md`
  (contexto, opciones, decisión, consecuencias).
- `temperature=0` en extracciones.
- Prompts versionados en `app/prompts/*.yaml` con campo `version`; cada traza registra la versión.

---

## 6. Conocimiento del dominio

| Tema | Qué dominar | Antes de | Prueba de dominio |
|------|-------------|----------|-------------------|
| Facturación electrónica | Actores, validación previa DIAN, CUFE, XML (UBL 2.1, `AttachedDocument`) vs representación gráfica; factura, notas crédito/débito, documento equivalente POS | Fase 0 | Explicar qué contiene un XML de factura y para qué sirve el CUFE |
| Documento soporte y cuenta de cobro | No obligados a facturar; documento soporte que genera el comprador; deducibilidad | Fase 0 | Clasificar 20 documentos sin dudar |
| Eventos RADIAN | Acuse, recibo del bien/servicio, aceptación expresa/tácita, reclamo; título valor | Fase 2 | Saber qué eventos hacen aceptada una factura |
| RUT y perfil tributario | NIT y DV, CIIU, responsabilidades casilla 53, régimen ordinario vs Simple, gran contribuyente, autorretenedor | Fase 0 | Leer un RUT y decir qué impuestos y retenciones aplican |
| IVA | 19 %, 5 %, exento vs excluido, IVA descontable | Fase 0 | Verificar a mano el IVA de 10 facturas |
| Retenciones | Retefuente por concepto con bases en UVT, ReteIVA, ReteICA municipal (Medellín), matriz quién retiene a quién | Fase 2 | Calcular el neto a pagar de 10 facturas |
| GMF y bancos | 4 por mil, comisiones, PSE, transferencias, referencias por banco | Fase 3 | Explicar todas las líneas de un extracto |
| Contabilidad básica | Partida doble, causación vs caja, CxC y CxP, NIIF pymes/micro (Ley 1314 de 2009), plan de cuentas | Fase 3 | Registrar a mano una compra con IVA y retención |
| Conciliación bancaria | Partidas conciliatorias, pagos parciales y agrupados, cierre mensual | Fase 3 | Conciliar a mano un mes pequeño |
| Calendario tributario | Retención mensual, IVA bimestral/cuatrimestral, renta, exógena, ICA; vencimientos por último dígito del NIT | Fase 5 | Saber qué necesita una pyme cada semana |
| Oficio del contador | Ley 43 de 1990, multiempresa, software contable (Siigo, Alegra, World Office, Helisa), formatos de importación | Fase 3 | Describir la jornada de cierre y dónde se pierde tiempo |
| Conservación y datos | Plazos de conservación, firmeza de declaraciones, Ley 1581 | Preparación | Redactar política de tratamiento y retención |

Fuentes: micrositios y cartillas de la DIAN, cursos virtuales del SENA, Actualícese, Gerencie.com.
**Contador asesor** desde la semana 1: valida guía de anotación (F0), taxonomía (F1), respuestas
de referencia del RAG (F2) y escenarios de conciliación (F3). Glosario en `docs/glosario.md`.

---

## 7. Preparación (antes de la semana 1)

1. Repositorio público `contable-ia`, licencia MIT, `.gitignore` Python + Node, `data/` ignorada.
2. Backend: `uv init apps/api`; `uv add fastapi "uvicorn[standard]" pydantic pydantic-settings sqlalchemy alembic "psycopg[binary]" celery redis instructor httpx lxml pymupdf`; `uv add --dev pytest ruff mypy`.
3. Frontend: `pnpm create next-app apps/web --ts --tailwind --app` + shadcn/ui.
4. `infra/docker-compose.yml`: `postgres` (imagen `pgvector/pgvector`, Postgres 16 o 17), `redis`, `minio`, `phoenix` opcional.
5. pre-commit: Ruff, mypy, Prettier, gitleaks.
6. `.env.example` con todas las variables; `.env` nunca se sube.
7. ADR 0001: monorepo FastAPI + Next.js; Postgres como única base (relacional + vectores + auditoría).
8. GitHub Projects: una columna por fase, una issue por paso.
9. Política de tratamiento de datos de una página y formato de autorización.
10. Cuentas: proveedor LLM (+ segundo para comparar), Langfuse Cloud (o Phoenix local), hosting.

**Criterio de salida:** `docker compose up` levanta todo; `uv run pytest` y `pnpm lint` en verde;
`ci.yml` corre en cada push.

---

## 8. Fase 0 · Datos y línea base (semanas 1–3)

**Resultado:** 250 documentos anonimizados y anotados, extractor v0 sin frameworks de agentes,
URL pública con la primera cifra de precisión por campo.

### 8.1 Corpus (semana 1)

| Tipo | Cantidad | Formato |
|------|----------|---------|
| Factura electrónica | 120 | ZIP con XML + PDF |
| Cuenta de cobro | 40 | Foto/escaneo/Word/PDF |
| RUT (formulario 001) | 30 | PDF |
| Extracto bancario | 30 | PDF |
| Contrato de servicios | 30 | PDF/Word |

- Fuentes: facturas propias, familiares/amigos con negocio, 2–3 contadores (a cambio de uso gratuito en F5). Autorización escrita.
- Sintéticos con Faker `es_CO` solo si faltan; marcados `synthetic=true`; nunca en el conjunto de prueba.
- `ml/anonymize.py`: Presidio + spaCy `es_core_news_lg` + reconocedores regex:
  - NIT `\b\d{3}\.?\d{3}\.?\d{3}-?\d\b`; cédula (6–10 dígitos junto a "C.C."/"cédula");
  - celular `(\+57\s?)?3\d{2}\s?\d{3}\s?\d{4}`; cuentas bancarias; correos; direcciones.
- Reemplazo por valores falsos **con el mismo formato** (NIT falso con DV válido), consistentes por documento. XML con `lxml`; PDF con PyMuPDF (`add_redact_annot` + `apply_redactions`) y texto falso encima. Tabla de correspondencias cifrada, solo local.
- **Revisión manual del 100 %** de los anonimizados.

### 8.2 Esquemas, guía y conjunto dorado (semana 2)

- Esquemas Pydantic v2 en `app/schemas/`: `Factura` (numero, cufe, fecha_emision, nit_emisor, dv_emisor, razon_social_emisor, nit_adquirente, subtotal, iva, retenciones, total, lineas), `CuentaCobro`, `RUT` (incluye CIIU y responsabilidades), `ExtractoBancario` (movimientos), `Contrato` (partes, objeto, valor, vigencia). Montos `Decimal`.
- Validadores de dominio:
  - DV del NIT (DIAN): dígitos de derecha a izquierda × 3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71; suma mod 11; residuo 0 o 1 → DV = residuo; si no, DV = 11 − residuo.
  - Fechas no futuras y en rango; `subtotal + iva − retenciones = total` (tolerancia $1); CUFE de 96 hex si existe.
- `evals/datasets/GUIA.md`: fechas ISO 8601, montos decimales sin miles, NIT sin puntos con DV aparte, ausente = `null`.
- Label Studio → `evals/datasets/golden/<split>/<doc_id>.json` (`split` = `dev`, `val` o `test`). Facturas: verdad generada desde el XML con parser determinista y revisada.
- Doble anotación del 20 %; acuerdo < 95 % por campo → corregir la guía.
- Partición 60/20/20 (dev/val/test) estratificada por tipo; **test congelado**.

### 8.3 Extractor v0 y aplicación (semanas 2–3)

- `app/extraction/router.py`: XML de factura → `lxml` (sin LLM); PDF con texto → Docling/PyMuPDF; imagen/escaneo → Tesseract `spa` (PaddleOCR si baja calidad); clasificación con LLM (`Literal` de tipos); extracción con Instructor al esquema del tipo; campos que no pasan validadores tras reintentos → `is_doubtful=true`.
- Registro de cada llamada LLM en `llm_calls`.
- BD (SQLAlchemy 2 + Alembic): `organizations`, `users`, `documents`, `extractions`, `extracted_fields` (`is_doubtful`, `corrected_value`), `llm_calls`, `audit_events`. RLS por `organization_id`.
- API: `POST /documents` (sube a MinIO/R2, encola Celery), `GET /documents/{id}`, `PATCH /fields/{id}` (corrección → `audit_events`).
- Web: login, carga múltiple, lista con estado, detalle con PDF a la izquierda y campos a la derecha (dudosos resaltados y editables).
- Despliegue: Dockerfile multi-etapa; Cloud Run/Fly.io (API + worker); Neon/Supabase; Vercel; R2/S3; `deploy.yml` en cada merge a `main`; dominio propio.

### 8.4 Línea base (semana 3)

- `evals/run_baseline.py` sobre **val**: coincidencia exacta normalizada (texto/fechas), tolerancia $1 (montos), conjuntos (listas). Informe: precisión por campo y tipo, % docs 100 % correctos, costo/doc, latencia p50/p95.
- Tabla de línea base en el README.

**Criterio de salida F0:** URL pública con login; 250 docs anonimizados y anotados; test congelado; informe de línea base; ADR 0002 ("Parser determinista para XML; LLM solo para formatos libres").

---

## 9. Fase 1 · Evals primero (semanas 4–6)

**Resultado:** ningún cambio entra a `main` sin evals; cada documento deja una traza.

### Semana 4 · Trazas y análisis de errores
1. Instrumentar con Langfuse (`@observe`) u OpenTelemetry + OpenInference (Phoenix): una traza por documento; spans `clasificar`, `ocr`, `extraer`, `validar`, `reintentar`; metadatos `doc_type`, `organization_id` anonimizado, modelo, versión de prompt, tokens, costo.
2. Prompts versionados (`app/prompts/*.yaml`).
3. **Codificación abierta:** 100 trazas con error del dev set; una nota libre por traza (`trace_id`, `nota`).
4. **Codificación axial:** agrupar en modos de falla con frecuencias → `evals/taxonomy.md`. Ej.: confusión de roles, formato numérico, campo inventado, OCR ilegible, tabla partida, clasificación errada.
5. Priorizar por frecuencia × impacto contable; atacar los 3 primeros en la semana 6.

### Semana 5 · Evals por código y jueces alineados
6. Evals por código primero (`evals/suites/test_extraction.py`): precisión por campo, validadores, matriz de confusión, suma de líneas vs subtotal.
7. Jueces LLM solo donde el código no alcanza: **uno por modo de falla, binario (pasa/no pasa) con justificación corta**, modelo distinto y más fuerte que el evaluado.
8. Alineación: ≥100 casos etiquetados a mano por juez (30–50 fallas); partición 20/40/40 (ejemplos/ajuste/prueba); reportar TPR, TNR y kappa de Cohen en `evals/judges/<juez>/alineacion.md`. **No usar jueces con TPR o TNR < 0,85.**
9. Empaquetar con DeepEval (`GEval` o métricas propias) dentro de pytest.

### Semana 6 · Puerta de CI, auditoría, iteración
10. `evals.yml`: en PR que toque `app/extraction/`, `app/prompts/`, `evals/`; suite rápida (50 docs dev); compara con el último artefacto de `main`; **falla** si precisión baja > 1 punto, si baja la tasa de validadores o si el costo/doc sube > 20 %; comenta tabla antes/después en el PR. `evals-nightly.yml`: val completo.
11. `audit_events`: `actor`, `accion`, `entidad`, `valor_anterior`, `valor_nuevo`, `modelo`, `version_prompt`, `trace_id`, `timestamp`; misma transacción; sin `UPDATE`/`DELETE`.
12. Página `/admin/calidad`: precisión en el tiempo, costo/doc, p95, modos de falla abiertos, alineación de jueces.
13. Iteración: hipótesis → rama → evals → aceptar solo si mejora sin regresiones; registrar todo (también fallidos) en `evals/CHANGELOG.md`.

**Criterio de salida F1:** trazas al 100 %; taxonomía publicada; ≥2 jueces alineados con cifras; CI bloqueando regresiones; auditoría inmutable; mejora medida vs línea base; ADR 0003 ("Evals por código antes que jueces; jueces binarios y alineados").

---

## 10. Fase 2 · RAG híbrido y ML clásico (semanas 7–10)

### RAG
1. Corpus con URL y fecha de consulta: Estatuto Tributario (Decreto 624 de 1989), DUR tributario (Decreto 1625 de 2016), resolución vigente de factura electrónica y su anexo técnico (verificar vigencia), conceptos DIAN sobre retención e IVA, contratos anonimizados (privados por organización).
2. Fragmentación estructural: uno por artículo/cláusula; metadatos `norma`, `articulo`, `titulo`, `url`, `fecha_consulta`, `organization_id` (null = público); artículos largos por parágrafo con "padre".
3. **Eval de recuperación antes del buscador:** 150 fragmentos → preguntas generadas → revisión manual (100) + 50 preguntas reales de contadores → `evals/datasets/retrieval.jsonl`.
4. Embeddings: comparar ≥2 (uno por API, uno abierto multilingüe tipo BGE-M3 / multilingual-E5-large).
5. Índices en Postgres: `embedding vector(n)` + HNSW; `tsv tsvector` (`spanish` + `unaccent`) + GIN; filtro obligatorio por `organization_id` en privados.
6. Top-30 de cada búsqueda → RRF (k=60) → re-ranker multilingüe (p. ej. `bge-reranker-v2-m3`) → top-5.
7. Tabla recall@5, recall@10, MRR, p95 para: vectores, texto, híbrida, híbrida+re-ranker. ADR 0004.
8. Generación anclada: solo contexto recuperado; cita por afirmación (`[E.T. art. 392]`); "no encontré soporte" si no alcanza; salida `respuesta`, `citas`, `confianza`; citas enlazadas en la UI.
9. Evals: citas válidas (código), fidelidad (juez alineado), exactitud vs 50 referencias con contador (juez), abstención en 15 fuera de alcance (código). Al `evals.yml`.
10. Advertencia "no reemplaza asesoría profesional"; tarea semanal de frescura (hash por artículo, reindexado incremental, vigencia).

### ML clásico
11. Conjunto aumentado inyectando anomalías etiquetadas: duplicados con número cambiado, montos ×10, IVA inconsistente, DV inválido, proveedor nuevo con monto alto.
12. **Modelo A (duplicados):** blocking (mismo NIT, monto ±1 %, fechas ±30 días); features (diferencia relativa, días, `rapidfuzz` de descripciones, mismo CUFE, mismo número con otro prefijo); LightGBM; PR-AUC y umbral con ≤1 falsa alarma por 20 alertas.
13. **Modelo B (anomalías):** Isolation Forest; features log(monto), z-score vs historial del proveedor, tarifa efectiva de IVA, nº de líneas, días desde la última factura; precisión@k (k = 5 % de facturas); **partición temporal**.
14. SHAP → frase en español por alerta.
15. MLflow: tracking (backend Postgres, artefactos S3/R2), métricas y gráficos, Model Registry con alias `champion`/`challenger`; la API carga por alias; `ml/training/train_anomalies.py` reproducible (semilla, versión de datos).
16. Feedback "Es correcta / Falsa alarma" → etiquetas reales; Evidently semanal de deriva.

**Criterio de salida F2:** tabla de recuperación; RAG con 4 evals en CI; 2 modelos en MLflow con SHAP; ADR 0004 y 0005.

---

## 11. Fase 3 · Agente gobernado y servidor MCP (semanas 11–14)

1. Grafo LangGraph: `cargar_periodo` → `emparejar_exacto` (código) → `emparejar_difuso` (candidatos por fecha y monto ajustado por retenciones; subconjuntos limitados para pagos agrupados; LLM solo en ambiguos) → `explicar_diferencias` (retefuente, ReteICA, 4 por mil, comisión, parcial, duplicado, sin explicar) → `aprobacion_humana` (`interrupt()`) → `registrar` (idempotente + auditoría) → `informe`.
2. Estado `TypedDict`: `periodo`, `facturas`, `movimientos`, `propuestas` (con `confianza`, `justificacion`), `decisiones`, `costo_acumulado`, `errores`.
3. Checkpointer `PostgresSaver`, `thread_id` por conciliación; reanuda tras reinicio.
4. `governance/policies.py`:

| Acción | Riesgo | Regla |
|--------|--------|-------|
| Leer documentos/normativa | Bajo | Sin aprobación |
| Proponer cruce | Bajo | Queda "propuesto" |
| Registrar cruce con confianza ≥ 0,9 | Medio | 1 aprobación (bloque permitido) |
| Registrar con confianza < 0,9 o diferencia sin explicar | Alto | Aprobación individual con comentario |
| Registrar por encima del monto definido por la pyme | Alto | 2 aprobaciones de personas distintas |

5. Lista blanca: el LLM solo tiene lectura + `proponer_cruce`; la escritura la llama solo `registrar`, que verifica la aprobación en BD.
6. Límites: tope de llamadas y costo por conciliación (p. ej. 50 llamadas o US$0,50) → informe parcial; `recursion_limit` explícito.
7. Inyección: texto de documentos delimitado como dato; caso de factura con instrucciones maliciosas en las evals.
8. Auditoría por transición, propuesta y decisión (`trace_id`, usuario, política, versión del grafo); línea de tiempo en la UI.
9. Pantalla de conciliación: tabla de propuestas, aprobar/rechazar/editar, bloque solo donde la política lo permite, filtro "requiere mi atención"; reanuda con `Command(resume=decisiones)`.
10. 20 escenarios sintéticos en `evals/datasets/conciliacion/` (parcial, agrupado, retenciones, 4 por mil, comisiones, duplicado, factura sin pago, movimiento sin factura, inyección).
11. Métricas: precisión/recall de cruces; diferencias bien explicadas; **matriz de fallas por transición** (nodo × tipo de error); **seguridad con tolerancia cero** (ningún registro sin aprobación; ninguna acción por inyección → CI falla); costo y pasos.
12. Servidor MCP (`services/mcp-server/`, FastMCP): `buscar_documentos`, `obtener_factura`, `consultar_normativa`, `estado_conciliacion`, `proponer_cruce` (solo propone). Token por organización, mismas políticas y filtros. Probar con MCP Inspector; demo grabada con un cliente MCP.
13. Trazas y auditoría también para llamadas MCP; escenario de cliente MCP intentando registrar sin aprobación.

**Criterio de salida F3:** agente con aprobación humana y reanudación; políticas en código; matriz de fallas publicada; 0 violaciones en 20 escenarios; MCP con demo; ADR 0006.

---

## 12. Fase 4 · Costo y modelo propio (semanas 15–18)

1. Tarea acotada: **texto OCR de cuenta de cobro o RUT → JSON del esquema**.
2. Destilación: ~2.000 textos (dev + sintéticos variados) → mejor API → conservar solo salidas que pasan **todos** los validadores y el juez de campo inventado → + golden dev. **Nunca test** (verificar con hash). Revisar licencia del proveedor sobre entrenar con sus salidas.
3. Formato chat del modelo base; `train.jsonl` / `val.jsonl` (90/10).
4. Base: modelo abierto pequeño (3–8 B) con buen español (variante instruct vigente de Qwen o similar); licencia comercial verificada.
5. QLoRA en GPU de 24 GB (RunPod/Modal) con Unsloth o TRL `SFTTrainer` + PEFT: 4 bits; r=16, alpha=32; dropout 0,05; lr 2e-4 con calentamiento 3 %; 2–3 épocas; 4.096 tokens; pérdida solo en la respuesta.
6. MLflow (hiperparámetros, curvas, hash de datos, métricas); adaptador a Hugging Face Hub con tarjeta de modelo.
7. Si no supera al base sin ajuste → revisar datos antes que hiperparámetros.
8. vLLM (API compatible OpenAI, `--enable-lora` o fusionado, salida estructurada con JSON schema); serverless con escala a cero; Ollama cuantizado para demo local.
9. Carga con Locust o k6: 50 concurrentes; p50/p95, docs/hora, arranques en frío.
10. Tabla en **test**: API grande, API pequeña, abierto sin ajuste, abierto + LoRA, enrutador → precisión por campo, docs 100 %, costo/1.000 docs, p50/p95. Costo propio = (USD/h GPU ÷ docs/h) + tiempo ocioso real.
11. Enrutador en cascada: XML → parser; libre → modelo propio; falla/baja confianza → API grande; falla → humano. Medir % por nivel y costo/precisión combinados (meta: ≤1 punto de pérdida de precisión).
12. Palancas: caché exacta por hash; caché de prompts del proveedor; API por lotes nocturna; caché semántica solo si su eval la respalda.
13. Costo al panel: por nivel, por conciliación, alerta de tope diario.

**Criterio de salida F4:** adaptador publicado; tabla comparativa en test; enrutador en producción con ahorro medido; ADR 0007.

---

## 13. Fase 5 · Usuarios reales y lanzamiento (semanas 19–22)

1. Pruebas automáticas de aislamiento entre organizaciones (documentos, campos, conciliaciones, fragmentos privados, MCP): todas deben fallar el acceso cruzado.
2. Seguridad: OWASP Top 10 y OWASP Top 10 LLM; secretos en gestor de la nube; rate limiting (`slowapi`); validación de archivos (tipo real, tamaño, páginas); logs sin PII; Sentry con filtrado; backups PITR con restauración probada; no retención en el proveedor LLM si existe.
3. Derechos del titular: autorización al registrarse, exportación y borrado total por organización (archivos, vectores, trazas), retención con tarea programada.
4. Reclutar 3–5 contadores/pymes (los de F0, red, comunidades de Medellín, LinkedIn); uso gratis a cambio de feedback semanal y caso anonimizado.
5. Incorporación de 30 min: autorización, organización, primer lote guiado.
6. Métricas: docs/semana; tasa de corrección por campo; tiempo ahorrado (20 docs manual vs herramienta); conciliaciones aprobadas sin edición; retención semana 4.
7. Feedback específico sí/no ("¿Este campo quedó bien?", "¿Este cruce es correcto?") con `trace_id`.
8. Rutina de calidad de los lunes (2 h): muestra de correcciones → anonimizar → dev set → codificación → taxonomía → un cambio validado por CI.
9. Evals en línea: jueces sobre 10 % de trazas de producción cada noche; alertas por umbral.
10. README inglés + `README.es.md`: problema, video 2 min + GIF, arquitectura, resultados línea base vs final (con fecha), metodología de evals, gobernanza, tabla de costos, índice de ADR, ejecución local con un comando y datos sintéticos, limitaciones.
11. Caso de estudio anonimizado con cifras.
12. Artículo técnico (inglés y español), comunidad técnica de Medellín, release `v1.0.0`.
13. Preparación de entrevistas: evals antes que agentes; alineación de jueces; gobernanza en código; modelo propio vs API; qué harías distinto.

**Criterio de salida F5:** ≥3 usuarios activos 4 semanas; métricas publicadas; rutina documentada; aislamiento en verde; README bilingüe; `v1.0.0`.

---

## 14. Riesgos y plan B

| Riesgo | Señal | Plan B |
|--------|-------|--------|
| < 250 documentos reales | < 100 al final de semana 1 | 150 reales + sintéticos marcados; priorizar XML |
| Gasto API se dispara | > US$40/mes | Suite rápida de 20 docs, API por lotes, caché exacta |
| Sin GPU | F4 en riesgo | Colab/Kaggle con modelo de 1–3 B; Ollama local |
| Sin usuarios | Semana 19 sin interesados | Procesar gratis un mes a un contador; declarar limitación |
| Normativa cambia | Fuentes desactualizadas | Tarea de frescura y vigencia visible en citas |
| Atraso > 3 semanas | F2 sin terminar en semana 12 | Recortar F4 a comparación sin ajuste; **nunca recortar evals ni gobernanza** |

---

## 15. Lista final del portafolio

- [ ] URL pública con cuenta demo y datos sintéticos
- [ ] README bilingüe, video 2 min, diagrama
- [ ] Línea base vs final con fechas
- [ ] Taxonomía y `evals/CHANGELOG.md` (con intentos fallidos)
- [ ] Jueces con TPR, TNR y kappa
- [ ] Puerta de CI visible en PRs
- [ ] Tabla de recuperación
- [ ] Modelos ML en MLflow con SHAP
- [ ] Agente con aprobación, auditoría y matriz de fallas
- [ ] Servidor MCP con demo
- [ ] Tabla costo/calidad/latencia y ahorro del enrutador
- [ ] Adaptador LoRA con tarjeta de modelo
- [ ] Pruebas de aislamiento en verde
- [ ] Métricas con usuarios reales y caso de estudio
- [ ] 7 ADR
- [ ] Artículo publicado y `v1.0.0`

---

## 16. Mapa de agentes

| Agente | Etapa | Secciones que lee |
|--------|-------|-------------------|
| Orquestador (sesión principal, `ORQUESTADOR.md`) | Todas; único que habla con el usuario | Todas |
| `preparacion-entorno` | Preparación | 3, 4, 5, 7 |
| `datos-corpus` | Fase 0 (8.1, 8.2) | 2, 5, 6, 8 |
| `extraccion-app` | Fase 0 (8.3, 8.4) | 3, 4, 5, 8 |
| `evals-calidad` | Fase 1 + revisor transversal de calidad y gobernanza | 2, 5, 9 y criterios de todas las fases |
| `rag-normativo` | Fase 2 (RAG) | 5, 6, 10 |
| `ml-anomalias` | Fase 2 (ML clásico) | 5, 10 |
| `agente-conciliacion` | Fase 3 | 2, 5, 6, 11 |
| `modelo-costos` | Fase 4 | 5, 12 |
| `lanzamiento-usuarios` | Fase 5 | 5, 13, 15 |
| `experto-contable` | Revisor transversal del dominio | 2, 6 |
