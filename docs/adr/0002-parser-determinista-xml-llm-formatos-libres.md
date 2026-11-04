# ADR 0002 · Parser determinista para XML; LLM solo para formatos libres

- **Estado:** propuesto (pendiente de la medición de línea base, INSTRUCCIONES.md §8.4)
- **Fecha:** 2026-11-04
- **Etapa:** Fase 0 · F0-09 (#19) y F0-10 (#20)

## Contexto

La factura electrónica DIAN llega como XML UBL 2.1 (suelto o dentro del `AttachedDocument` del ZIP
del facturador) y trae todos los campos estructurados. Cuentas de cobro, RUT, extractos y contratos
llegan como PDF o imagen, sin estructura. La regla dura 7 pide LLM solo donde el código no alcanza
y la 9 exige registrar el costo de cada llamada. El presupuesto LLM es de US$10–40/mes.

## Opciones

1. LLM para todo (más simple, pero paga y arriesga errores donde el dato ya viene exacto).
2. **Cascada:** XML → parser `lxml`; PDF con texto → pypdfium2; imagen/escaneo → Tesseract `spa`;
   texto → clasificación y extracción con LLM (Instructor) al esquema Pydantic del tipo.
3. Docling para todo el texto de PDF (mejor con tablas, pero modelos pesados para un equipo con
   ~6 GB de RAM libre y un worker en la nube pequeño).

## Decisión

Opción 2 (`apps/api/app/extraction/router.py`):

- **XML/ZIP**: parser determinista, sin LLM. Mapeo de campos = `evals/datasets/GUIA.md` §4. Un
  valor del XML que no pasa el esquema se anula y se marca dudoso (nunca se corrige a mano). Notas
  crédito/débito se leen con el esquema `Factura` y van a `needs_review` hasta tener esquema propio.
- **PDF**: pypdfium2 (Apache-2.0/BSD-3). Sin capa de texto (≥ 25 caracteres visibles por página en
  promedio) se trata como escaneado. Docling queda como opción si las tablas de extractos fallan.
- **OCR**: Tesseract `spa` vía pytesseract. Si no está instalado, la ruta falla con un error claro.
- **LLM**: interfaz `LLMClient` (Anthropic, OpenAI o vLLM por `.env`) con Instructor y
  `temperature=0` fija en código. Instructor hace **un** intento por llamada; los reintentos
  (acotados por `LLM_MAX_RETRIES`) los hace el extractor con los errores del esquema y de los
  validadores de dominio, para que cada intento quede en `llm_calls` y respete el tope. Tras los
  reintentos, los campos que siguen sin validar quedan `is_doubtful=true`.
- **Costo**: cada llamada escribe `llm_calls` en su propia transacción. Sin precio del modelo en la
  tabla (`app/llm/prices.yaml`) o sin `LLM_MAX_COST_PER_DOC_USD`, no se llama (falla cerrado). Al
  superar el tope se detiene y el documento va a `needs_review`.

## Consecuencias

- Las facturas con XML cuestan US$0 y su precisión depende solo del parser (probado campo a campo).
- El tope se puede rebasar como máximo en una llamada (se verifica antes de cada una).
- Instructor no hace reintentos internos: un cambio de versión que altere `max_retries=0` lo
  detectan las pruebas con el cliente falso.
- Pendiente: medir en **val** (F0-15) y revisar esta decisión con las cifras de la línea base.
