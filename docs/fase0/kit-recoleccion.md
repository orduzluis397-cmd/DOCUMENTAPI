# Kit de recolección de documentos · Fase 0, semana 1

> Guía práctica para el dueño del proyecto. Responde al paso 9 de Preparación y al §8.1 de
> `INSTRUCCIONES.md`: conseguir **250 documentos reales con autorización escrita**.
> **Versión:** 0.1 · 2026-11-03 · elaborada por el agente `datos-corpus`.
> Los pasos de portales (DIAN, bancos) marcados `[verificar]` pueden cambiar de nombre o de menú;
> confírmalos la primera vez que los hagas.

## 0. Antes de pedir un solo documento

1. **Autorización primero.** Nadie entrega documentos sin firmar antes
   `docs/legal/autorizacion-uso-documentos.md` (todavía es borrador; el abogado debe revisarlo antes
   de usarlo con terceros). Para tus documentos propios, firma una igual: así queda la trazabilidad.
2. Asigna a cada autorización un código `AUT-001`, `AUT-002`, … y a cada fuente un código
   `F001`, `F002`, … Los dos códigos van al inventario. **El nombre real de la persona no va al
   inventario ni a los nombres de carpeta**: solo aparece en la autorización firmada, que guardas
   aparte (física o en `data/autorizaciones/`).
3. Ten lista la copia local del inventario: copia `docs/fase0/inventario-plantilla.csv` a
   `data/inventario.csv` (dentro de `data/`, que está ignorada por git) y borra la fila `EJEMPLO`.

## 1. Cuotas

| Tipo | Meta | Formato esperado | Fuente principal | Corte de referencia (40 %) |
|------|------|------------------|------------------|----------------------------|
| Factura electrónica | **120** | ZIP con XML + PDF (el ZIP completo, sin descomprimir) | Correo de facturas recibidas; contadores | 48 |
| Cuenta de cobro | **40** | Foto, escaneo, Word o PDF | Amigos/familiares independientes; contadores | 16 |
| RUT (formulario 001) | **30** | PDF | Portal DIAN; proveedores; contadores | 12 |
| Extracto bancario | **30** | PDF descargado de la banca en línea | Cuentas propias y de familiares con negocio | 12 |
| Contrato de servicios | **30** | PDF o Word | Contratos propios, de independientes, de contadores | 12 |
| **Total** | **250** | | | **100** |

La columna "corte de referencia" no es una meta: reparte por tipo el umbral de la señal de riesgo.
Si al final de la semana 1 el **total** real está por debajo de 100, se evalúa el plan B (sección 7).

Prioridad cuando el tiempo apriete: **facturas en ZIP** primero (su verdad sale del XML con parser,
son el 110 de 140 del caso guía de §2), luego extractos y cuentas de cobro (que el caso guía usa en
la conciliación y en la consulta normativa), luego RUT y contratos.

## 2. De dónde sacar cada tipo

### 2.1 Facturas electrónicas (ZIP con XML + PDF)

**Lo que necesitamos es el ZIP tal como lo envía el emisor.** Trae el XML (`AttachedDocument`, que
envuelve la factura y la respuesta de validación de la DIAN) y el PDF (representación gráfica). El
PDF solo **no sirve** como factura: la verdad de los campos sale del XML.

**Desde el correo (la vía más rápida):**

1. En el buzón donde llegan las facturas de compra (Gmail, Outlook…), busca: `has:attachment
   filename:zip factura` o `"factura electrónica"` o `"ad0"` (muchos ZIP empiezan con `ad`/`z`
   seguido del NIT) `[verificar patrones por proveedor tecnológico]`.
2. Descarga el **adjunto `.zip`** sin abrirlo ni descomprimirlo. Si el correo trae el XML y el PDF
   sueltos (sin ZIP), descarga los dos y guárdalos juntos con el mismo nombre base.
3. Algunos proveedores tecnológicos envían solo un enlace: entra y descarga el paquete "XML + PDF"
   o "AttachedDocument".
4. Toma facturas de **varios meses y varios emisores** (no 120 del mismo proveedor).

**Desde el servicio de la DIAN (cuando no están en el correo):**

1. Entra al portal de factura electrónica de la DIAN: catálogo de facturación
   (`catalogo-vpfe.dian.gov.co`) → "Documentos recibidos" `[verificar ruta vigente]`.
2. Ingresa como persona natural o empresa; la DIAN envía un **token de acceso** al correo
   registrado en el RUT.
3. Filtra por rango de fechas y descarga los documentos. Revisa qué entrega la descarga: si trae
   solo el XML o el PDF, anótalo en `notas` del inventario (el ZIP original del emisor es mejor).

**Notas crédito y débito:** entran en esta cuota (se marcan `tipo_documento = nota_credito` o
`nota_debito`). Busca al menos **5 notas crédito** y, si aparecen, algunas notas débito.

### 2.2 Cuentas de cobro

- Pide a personas que trabajan como independientes (no obligadas a facturar) las cuentas de cobro que
  han emitido, o a una pyme las que ha recibido.
- Sirven todos los formatos: Word, PDF, **fotos con el celular** y escaneos. Las fotos chuecas o con
  sombra son **valiosas** (el caso guía tiene 18 fotos de cuentas de cobro).
- No reconstruyas ni "limpies" una cuenta de cobro: guárdala tal como llegó.

### 2.3 RUT (formulario 001)

- **El tuyo y el de tu negocio:** portal DIAN (`dian.gov.co`) → "Usuario registrado" → ingresa con
  tu cuenta → "Obtener copia RUT" o "Consultar RUT" → descarga el PDF `[verificar ruta vigente]`.
- **De terceros:** los proveedores suelen enviar su RUT cuando se les crea como proveedor; los
  contadores tienen el de cada cliente. Pide el PDF descargado del portal, no una foto, salvo que
  quieras unos pocos ejemplos de mala calidad.
- Busca variedad: persona natural y jurídica, Régimen Simple, responsable y no responsable de IVA,
  gran contribuyente, autorretenedor (casilla 53 distinta).

### 2.4 Extractos bancarios

- En la banca en línea de cada banco: "Extractos" o "Certificados y extractos" → elige la cuenta y
  el mes → descarga en **PDF** `[verificar menú por banco]`. Si hay opción Excel/CSV, descarga
  también el PDF: el PDF es el que se va a procesar.
- Si el banco envía el extracto por correo con contraseña (normalmente la cédula), **no anotes la
  contraseña en el inventario**: abre el PDF, guárdalo sin protección con "Imprimir a PDF" o pídele
  a quien te lo dio que lo haga. Anota en `notas` "venía con contraseña".
- Busca **varios bancos** (Bancolombia, Davivienda, Banco de Bogotá, BBVA, Nequi/Daviplata si hay
  negocio que los use, cooperativas) y meses con movimientos de PSE, transferencias, 4 por mil y
  comisiones.
- Ideal: extractos del **mismo mes y negocio** que algunas de las facturas recolectadas. Eso permite
  construir escenarios de conciliación reales en la fase 3. Anótalo en `notas`
  ("mismo negocio que F003, octubre").

### 2.5 Contratos de servicios

- Contratos de prestación de servicios de independientes, de arrendamiento de servicios, de
  mantenimiento, de asesoría. PDF o Word.
- Sirven firmados y escaneados, y también la versión en Word.
- Evita contratos laborales (traen datos de nómina y seguridad social; ver sección 4).

## 3. Variedad deseada

Mejor 120 facturas de 40 emisores que 120 de 3. Al recolectar, apunta a:

| Dimensión | Qué buscar |
|-----------|------------|
| Emisores | Al menos **30 emisores distintos** de factura; distintos proveedores tecnológicos (cambia el formato del ZIP y del PDF). |
| Tipos de factura | Bienes y servicios; con IVA 19 %, 5 %, exentos y excluidos; con y sin retenciones; varias líneas y una sola línea. |
| Notas | Al menos 5 notas crédito; notas débito si aparecen. |
| Personas | Persona natural y jurídica, como emisor y como adquirente. |
| Bancos | Al menos **4 bancos** distintos en los extractos. |
| Calidad | Al menos **10 fotos de mala calidad** (cuentas de cobro, alguna factura impresa, algún RUT): ladeadas, con sombra, borrosas pero legibles. |
| Periodo | Varios meses y, si se puede, de 2025 y 2026 (cambian formatos y versiones del anexo técnico). |
| Ciudades | No solo Medellín: el ReteICA y los formatos cambian por municipio. |

## 4. Qué NO recolectar

No pidas, no guardes y, si llega por error, **borra y avisa a quien lo envió**:

- **Datos de menores de edad**: documentos donde un menor aparezca como titular, beneficiario o
  contratante (p. ej. facturas de colegios o pensiones a nombre del menor, contratos con menores).
- **Datos sensibles** (Ley 1581, art. 5): historias clínicas, facturas o cuentas de servicios de
  salud con diagnóstico, datos de afiliación sindical, religiosa o política, datos biométricos.
- **Documentos de identidad**: fotos de cédula, pasaporte o licencia.
- **Nómina y seguridad social**: desprendibles de pago, planillas PILA, contratos laborales,
  certificados de ingresos y retenciones de empleados.
- **Credenciales**: contraseñas, tokens DIAN, claves de firma electrónica (`.p12`, `.pfx`), códigos
  de acceso a banca. Nunca se anotan en ningún archivo del proyecto.
- **Tarjetas**: extractos de tarjeta de crédito con el número completo visible.
- Documentos de alguien que no firmó la autorización o de quien la persona no puede disponer
  (ver sección 5 de la autorización).

## 5. Cómo entregarlos y guardarlos

**Dónde:** únicamente en tu equipo, en `data/raw/<id_fuente>/`, una carpeta por fuente con su
código (no con el nombre de la persona):

```
data/
  inventario.csv            ← copia llena de la plantilla (local, nunca al repo)
  autorizaciones/           ← autorizaciones firmadas escaneadas (opcional)
  raw/
    F001/                   ← tus documentos propios
      factura/  cuenta_cobro/  rut/  extracto/  contrato/
    F002/                   ← contador 1
    F003/                   ← familiar con negocio
```

Las subcarpetas por tipo son opcionales pero ayudan al inventario. Conserva los nombres de archivo
originales (sobre todo el de los ZIP).

**Cómo te los entregan:** los medios que lista la autorización: en físico (tú escaneas), por correo
directo a ti o por un **enlace seguro** con caducidad (Drive o OneDrive compartido solo contigo).
Al recibirlos, cópialos a `data/raw/<id_fuente>/` y borra la copia del correo, del chat o de la
carpeta de descargas. Evita grupos de WhatsApp y enlaces públicos.

**Reglas que no se negocian (regla dura 1):**

- **Nunca por el chat**: no pegues ni adjuntes un documento sin anonimizar en una conversación con
  Claude, ChatGPT ni ningún asistente o API externa. Ni para "probar rápido".
- **Nunca al repositorio**: `data/` está en `.gitignore`; no la saques de ahí, no la renombres, no
  copies documentos a `docs/`, `evals/` ni a ningún otro sitio del repo.
- **Nunca a una API externa** (LLM, OCR en la nube, conversores en línea de PDF/imagen) antes de
  anonimizar y de tu revisión manual del 100 %.
- Ningún agente abre `data/raw/` para leer contenido en esta etapa: el agente `datos-corpus` solo
  cuenta archivos para el inventario cuando empiece la Fase 0.

**Cada vez que recibas un lote**, agrega una fila al inventario (`data/inventario.csv`):
`id_fuente`, tipo, formato, cantidad, fecha y código de la autorización. Deja `anonimizado` y
`revisado_100` en `no`: se llenan después.

### 5.1 Valores del inventario

| Columna | Valores |
|---------|---------|
| `id_fuente` | `F001`, `F002`, … (una por persona o empresa que entrega) |
| `fuente` | Categoría, **sin nombres**: `propio`, `familiar`, `amigo`, `contador`, `proveedor` |
| `tipo_documento` | `factura`, `nota_credito`, `nota_debito`, `cuenta_cobro`, `rut`, `extracto`, `contrato` |
| `formato` | `zip_xml_pdf`, `xml_pdf_sueltos`, `xml`, `pdf`, `foto`, `escaneo`, `word` |
| `cantidad` | Número de documentos del lote (un ZIP = 1 documento) |
| `fecha_recibido` | `AAAA-MM-DD` |
| `autorizacion_id` | `AUT-###` de la autorización firmada |
| `anonimizado` / `revisado_100` | `no` al recibir; `si` cuando se anonimice y cuando tú revises a mano el 100 % |
| `notas` | Calidad, periodo, banco, relación con otra fuente; **nunca datos personales ni contraseñas** |

Una fila por lote y tipo: si `F003` entrega 12 facturas y 2 extractos, son dos filas.

## 6. Ritmo sugerido para la semana 1

| Día | Acción |
|-----|--------|
| 1 | Descarga tus facturas del correo, tus RUT y tus extractos. Envía los mensajes a 3 contadores y a 5–8 conocidos con negocio (`docs/fase0/mensajes-solicitud.md`). |
| 2–3 | Firma de autorizaciones; primeros lotes; inventario al día. |
| 4 | Recordatorio a quien no respondió (mensaje 3). |
| 5 | **Corte**: suma el inventario por tipo y repórtalo al orquestador. |

## 7. Señal de riesgo y plan B (§14)

| Señal | Plan B |
|-------|--------|
| **Menos de 100 documentos reales al final de la semana 1** | Bajar la meta a **150 reales + sintéticos marcados** (`synthetic=true`, generados con Faker `es_CO`), **priorizando facturas en ZIP con XML**. Los sintéticos nunca van al conjunto de prueba. |

Activar el plan B es una decisión que toma el usuario con el orquestador al cierre de la semana 1;
no se activa en silencio. Hasta entonces, la meta sigue siendo 250.

## 8. Lista de chequeo rápida

- [ ] Autorización firmada antes de recibir documentos, con código `AUT-###`.
- [ ] Fuente con código `F###`; sin nombres reales en carpetas ni en el inventario.
- [ ] Documentos en `data/raw/<id_fuente>/`, nada fuera de `data/`.
- [ ] Facturas como ZIP completo (XML + PDF).
- [ ] Nada de menores, salud, cédulas, nómina ni credenciales.
- [ ] Copias en correo/chat/descargas borradas tras pasar a `data/raw/`.
- [ ] Fila nueva en `data/inventario.csv` por cada lote.
- [ ] Ningún documento pegado en un chat ni enviado a un servicio en línea.
