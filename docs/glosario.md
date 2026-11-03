# Glosario de Contable IA

> Vocabulario común del dominio contable y tributario colombiano para todos los agentes y para la
> documentación del producto. Agrupado por los temas de `INSTRUCCIONES.md` §6.
>
> **Mantiene:** agente `experto-contable` (por encargo del orquestador). **Valida:** contador asesor.
> **Versión:** 0.1 · 2026-11-03 · estado: borrador, pendiente de validación del contador asesor.

## Cómo leer este glosario

- **Norma:** referencia normativa principal. Las marcadas `[verificar]` no tienen certeza suficiente
  y no deben citarse en prompts, respuestas del RAG ni validadores hasta confirmarlas. Las no
  marcadas son referencias establecidas, pero **solo las de la sección "Fuentes consultadas" se
  contrastaron con una fuente en línea en esta versión**; el resto se contrastará contra el texto
  oficial cuando se arme el corpus del RAG (§10, paso 1).
- **En el sistema:** dónde aparece el término (campo del esquema de §8.2, validador, nodo del grafo de
  §11 o paso del caso guía de §2). "Previsto" = aún no existe en el código.
- **Parámetro con vigencia (regla dura 8):** las cifras que cambian por año o por norma (valor de la
  UVT, bases, tarifas, topes, plazos del calendario) **no se escriben aquí como valor fijo**. Viven en
  tablas con `vigente_desde` / `vigente_hasta` y fuente. Se indican como `⟨parámetro⟩`.
- Abreviaturas: **E.T.** = Estatuto Tributario (Decreto 624 de 1989); **DUR** = Decreto Único
  Reglamentario en materia tributaria (Decreto 1625 de 2016); **C. Co.** = Código de Comercio
  (Decreto 410 de 1971).

---

## 1. Facturación electrónica

| Término | Definición | Norma | En el sistema |
|---|---|---|---|
| **Factura electrónica de venta** | Factura que se expide, valida por la DIAN y entrega en formato electrónico (XML). Es el soporte de ingresos del vendedor y de costos, deducciones e IVA descontable del comprador. | E.T. arts. 615, 616-1, 617; Resolución DIAN 000165 de 2023 | Esquema `Factura`; tipo de documento en la clasificación; paso 1–2 del caso guía (110 ZIP). |
| **Facturador electrónico** | Sujeto obligado o voluntario habilitado ante la DIAN para facturar electrónicamente. Responsabilidad 52 en el RUT. | Resolución 000165 de 2023 | Perfil del emisor (RUT, casilla 53). |
| **Habilitación** | Proceso ante la DIAN (set de pruebas) para quedar autorizado a emitir factura electrónica, por sí mismo o con proveedor tecnológico. | Resolución 000165 de 2023 | — |
| **Proveedor tecnológico** | Empresa autorizada por la DIAN que genera, transmite y entrega facturas por cuenta del facturador. | E.T. art. 616-4 `[verificar]` | Ayuda a reconocer el formato del ZIP según el emisor. |
| **Validación previa** | La DIAN valida la factura **antes** de que se entregue al adquirente; sin validación exitosa no hay factura. | E.T. art. 616-1 | El parser verifica que el ZIP traiga la respuesta de validación (`ApplicationResponse`). |
| **Numeración / resolución de facturación** | Rango de numeración autorizado por la DIAN, con prefijo y vigencia, que debe usar el facturador. | Resolución 000165 de 2023 | Campo `numero` (prefijo + consecutivo). Útil en el modelo A de duplicados ("mismo número con otro prefijo"). |
| **CUFE** (Código Único de Factura Electrónica) | Identificador único de cada factura, calculado con SHA-384 sobre datos de la factura (número, fecha, valores, NIT, clave técnica). Se representa como **96 caracteres hexadecimales**. Permite consultar la factura en la DIAN y detectar duplicados. | Anexo técnico de factura electrónica (versión vigente: 1.9 `[verificar vigencia]`) | Campo `Factura.cufe`; validador "CUFE de 96 hex si existe" (§8.2); feature "mismo CUFE" del modelo de duplicados. |
| **CUDE** (Código Único de Documento Electrónico) | Equivalente del CUFE para documentos distintos de la factura de venta: notas crédito y débito, documento equivalente electrónico, eventos. | Anexo técnico, Resolución 000165 de 2023 | Previsto: campo de identificador en notas; no confundir con `cufe`. |
| **CUDS** | Código único del documento soporte electrónico. | Resolución 000167 de 2021 y anexo técnico `[verificar nombre y algoritmo]` | Previsto en el esquema de documento soporte. |
| **UBL 2.1** | Estándar XML (OASIS Universal Business Language) que la DIAN adoptó, con extensiones propias, como formato de la factura y demás documentos electrónicos. | Anexo técnico | `app/extraction/`: el XML se procesa con `lxml`, sin LLM (regla dura 7, ADR 0002). |
| **`AttachedDocument`** | Contenedor UBL que el emisor entrega al adquirente: envuelve el XML de la factura y la respuesta de validación de la DIAN (`ApplicationResponse`). Es el XML que normalmente viene dentro del ZIP. | Anexo técnico | El parser debe desempaquetar `AttachedDocument` → `Invoice` (a menudo como CDATA) antes de leer campos. |
| **`ApplicationResponse`** | Mensaje UBL de respuesta: lo usa la DIAN para informar el resultado de la validación y lo usan las partes para los eventos (acuse, aceptación, reclamo). | Anexo técnico; Resolución 000085 de 2022 | Prueba de validación previa; previsto para eventos RADIAN. |
| **Representación gráfica** | Versión visual (normalmente PDF) de la factura, con CUFE y código QR. **No es la factura**: la factura es el XML. | Resolución 000165 de 2023 | El PDF del ZIP se muestra en la UI; la verdad de los campos sale del XML (§8.2: "verdad generada desde el XML"). |
| **Adquirente** | Comprador que recibe la factura. | — | Campo `Factura.nit_adquirente`. En el caso guía, la ferretería es adquirente de sus ~130 compras. |
| **Emisor / obligado a facturar** | Vendedor que expide la factura. | E.T. art. 615 | `nit_emisor`, `dv_emisor`, `razon_social_emisor`. |
| **Nota crédito** | Documento electrónico que disminuye o anula (total o parcialmente) una factura ya expedida: devoluciones, descuentos, errores. Debe referenciar la factura. | Resolución 000165 de 2023 | Previsto: tipo de documento; en conciliación explica pagos menores al valor facturado. |
| **Nota débito** | Documento electrónico que aumenta el valor de una factura ya expedida (intereses, ajustes de precio). Referencia la factura. | Resolución 000165 de 2023 | Previsto: tipo de documento. |
| **Documento equivalente** | Documento que puede usarse en lugar de la factura en ciertas operaciones (tiquete POS, boletas, servicios públicos, transporte, etc.). | E.T. art. 616-1; Resolución 000165 de 2023 | Clasificación de "varios" del paso 1. |
| **Documento equivalente electrónico tiquete POS** | Tiquete de máquina registradora (POS) expedido electrónicamente y validado por la DIAN. Por encima de un tope, el comprador puede exigir factura electrónica. | Resolución 000165 de 2023 | Tope en UVT = `⟨parámetro⟩`. Importante para deducibilidad de compras pequeñas. |
| **Líneas / ítems** | Detalle de bienes o servicios de la factura: descripción, cantidad, valor unitario, impuestos por línea. | Anexo técnico (`InvoiceLine`) | Campo `Factura.lineas` (lista; evaluación por conjuntos, §8.4). |
| **Subtotal / base gravable** | Valor antes de impuestos sobre el que se calcula el IVA. | — | `Factura.subtotal` (`Decimal`). |
| **Total / valor a pagar** | Valor final de la factura. Ver la nota de la sección 6 sobre retenciones en el XML. | Anexo técnico (`LegalMonetaryTotal`) | `Factura.total`; validador de totales. |

## 2. Documento soporte y cuenta de cobro

| Término | Definición | Norma | En el sistema |
|---|---|---|---|
| **No obligado a facturar** | Persona (típicamente natural, no responsable de IVA, con ciertos topes) que no tiene que expedir factura. | E.T. art. 616-2; DUR (art. 1.6.1.4.3 `[verificar]`) | Determina, al leer el RUT o la cuenta de cobro, si hace falta documento soporte. |
| **Cuenta de cobro** | Documento informal (no regulado como tal) con el que un no obligado a facturar cobra un servicio o venta. Por sí sola **no** soporta costos ni deducciones del comprador. | Sin norma propia `[verificar con contador]` | Esquema `CuentaCobro`; 18 fotos en el paso 1; tarea del modelo propio en fase 4. |
| **Documento soporte en adquisiciones a no obligados a facturar** | Documento electrónico que **genera el comprador** cuando le compra a un no obligado a facturar; con él soporta costos, deducciones e impuestos descontables. Se transmite a la DIAN. | E.T. art. 771-2; Resolución 000167 de 2021 (mod. Res. 000488 de 2022) | Respuesta de referencia del RAG del paso 6 ("¿debo generar documento soporte por las cuentas de cobro?"). |
| **Deducibilidad / procedencia de costos** | Requisito para que un costo o gasto se acepte en renta y su IVA sea descontable: tener factura electrónica o documento soporte con los requisitos legales. | E.T. arts. 771-2, 771-5 (pagos en efectivo) | Previsto: alerta "compra sin soporte válido". |
| **Nómina electrónica** (documento soporte de pago de nómina) | Soporte electrónico de pagos laborales. Fuera del alcance de la primera versión. | Resolución DIAN 000013 de 2021 `[verificar]` | Fuera de alcance. |

## 3. Eventos RADIAN y factura como título valor

| Término | Definición | Norma | En el sistema |
|---|---|---|---|
| **RADIAN** | Registro de la Factura Electrónica de Venta como Título Valor: plataforma DIAN donde se registran los eventos que permiten que la factura circule (endoso, factoring). | Decreto 1154 de 2020 (compilado en Decreto 1074 de 2015); Resolución 000085 de 2022 | Previsto en fase 2 (RAG) y como estado de la factura. |
| **Evento** | Mensaje electrónico (`ApplicationResponse`) que deja constancia de un hecho sobre la factura. Códigos del anexo: 030 acuse, 031 reclamo, 032 recibo del bien/servicio, 033 aceptación expresa, 034 aceptación tácita `[verificar códigos]`. | Resolución 000085 de 2022 | Previsto: tabla de eventos por factura. |
| **Acuse de recibo** | Evento con el que el adquirente informa que **recibió la factura** (no que la acepta). | Resolución 000085 de 2022 | — |
| **Recibo del bien o prestación del servicio** | Evento con el que el adquirente informa que recibió la mercancía o el servicio. Desde ahí corre el plazo de la aceptación tácita. | Resolución 000085 de 2022; C. Co. art. 773 | — |
| **Aceptación expresa** | Evento con el que el adquirente acepta la factura de forma explícita. | C. Co. art. 773; Decreto 1074 de 2015 (mod. Decreto 1154 de 2020) | — |
| **Aceptación tácita** | La factura se entiende aceptada si el adquirente no reclama dentro de los **tres días hábiles** siguientes a la recepción de la mercancía o del servicio. El emisor deja constancia en RADIAN. | C. Co. art. 773; Decreto 1074 de 2015, art. 2.2.2.53.4 (mod. Decreto 1154 de 2020) | Plazo como `⟨parámetro⟩` aunque hoy sea fijo en la ley. |
| **Reclamo** | Evento con el que el adquirente rechaza la factura (total o parcialmente) e indica el motivo. Impide la aceptación. | Resolución 000085 de 2022 | — |
| **Título valor** | Documento negociable que incorpora un derecho de crédito. La factura aceptada y registrada en RADIAN puede endosarse. | C. Co. arts. 619, 772–774 | — |

## 4. RUT y perfil tributario

| Término | Definición | Norma | En el sistema |
|---|---|---|---|
| **RUT** (Registro Único Tributario) | Registro de la DIAN que identifica a cada contribuyente y sus obligaciones. Se lee en el **formulario 001**. | E.T. art. 555-2 | Esquema `RUT`; 30 docs del corpus; "1 RUT nuevo" del paso 1. |
| **NIT** | Número de Identificación Tributaria asignado por la DIAN. En personas jurídicas suele tener 9 dígitos; en personas naturales es el número de cédula (longitud variable). | E.T. art. 555-1 | Campos `nit_emisor`, `nit_adquirente`: **sin puntos y sin DV** (`GUIA.md`). Ojo: la regex del anonimizador (§8.1) solo cubre 9 dígitos. |
| **DV** (dígito de verificación) | Dígito que acompaña al NIT (`800197268-4`) y detecta errores de digitación. Ver algoritmo abajo. | Algoritmo DIAN (módulo 11) | Campo `dv_emisor`; validador de dominio (paso 3); anomalía inyectada "DV inválido" (fase 2). |
| **CIIU** | Código de actividad económica (Clasificación Industrial Internacional Uniforme, revisión 4 adaptada para Colombia por el DANE). Casillas 46–50 del RUT `[verificar casillas]`. Incide en ReteICA y en la tarifa del Simple. | Resolución DIAN 000114 de 2020 `[verificar]` | Campo del esquema `RUT` (CIIU principal y secundarios). |
| **Responsabilidades (casilla 53)** | Lista codificada de obligaciones del contribuyente en el RUT. Códigos frecuentes: **05** renta régimen ordinario; **07** retención en la fuente a título de renta; **13** gran contribuyente; **14** informante de exógena; **15** autorretenedor; **42** obligado a llevar contabilidad `[verificar]`; **47** Régimen Simple; **48** responsable de IVA; **49** no responsable de IVA; **52** facturador electrónico. El código **09** (retención en la fuente en IVA) fue **retirado de oficio por la DIAN**: los RUT antiguos pueden mostrarlo. | Resolución DIAN vigente sobre RUT `[verificar lista oficial completa]` | Campo `RUT.responsabilidades` (lista de códigos). Base del perfil tributario y de la matriz de retenciones. Los códigos son catálogo con vigencia, no `Enum` cerrado en código. |
| **Régimen ordinario** | Régimen general del impuesto de renta (responsabilidad 05). | E.T. Libro I | Perfil tributario. |
| **Régimen Simple de Tributación (SIMPLE)** | Régimen opcional que unifica renta y otros impuestos en un pago con tarifa por actividad e ingresos. Sus contribuyentes, en general, **no son sujetos de retención en la fuente** en renta y no actúan como agentes de retención salvo excepciones. | E.T. arts. 903–916 (Ley 2155 de 2021, Ley 2277 de 2022) `[verificar excepciones vigentes, art. 911]` | Responsabilidad 47; regla de la matriz de retenciones. |
| **Responsable de IVA** | Quien debe cobrar, declarar y pagar IVA (responsabilidad 48). | E.T. art. 437 | En el caso guía, la ferretería lo es. |
| **No responsable de IVA** | Persona natural que cumple los topes y condiciones para no cobrar IVA (responsabilidad 49). Topes en UVT = `⟨parámetro⟩`. | E.T. art. 437, parágrafo 3 | Indicador de "factura con IVA de un no responsable" (anomalía). |
| **Gran contribuyente** | Contribuyente así calificado por resolución de la DIAN según su tamaño (responsabilidad 13). Es agente de retención y de ReteIVA. La lista cambia por resolución. | E.T. art. 562; resolución DIAN de calificación `[verificar la vigente]` | Responsabilidad 13; lista como `⟨parámetro⟩` con vigencia. |
| **Agente de retención** | Quien por ley debe practicar retención en los pagos que hace (personas jurídicas, personas naturales que cumplan topes, etc.). | E.T. art. 368 y ss. | En el caso guía, la ferretería es agente de retención. |
| **Autorretenedor** | Contribuyente autorizado (o obligado) a practicarse la retención a sí mismo; por eso **el pagador no le retiene** en renta en los conceptos de la autorización (responsabilidad 15). Existe además la autorretención especial de renta de personas jurídicas. | E.T. art. 368; DUR (autorretención especial, art. 1.2.6.6 y ss.) `[verificar]` | Regla de la matriz de retenciones: si el proveedor es autorretenedor, no se espera retefuente en el pago. |
| **Obligado a llevar contabilidad** | Comerciantes y otros obligados por ley a llevar contabilidad conforme a NIIF. | C. Co. art. 19; E.T. art. 364-5 `[verificar]` | Perfil tributario. |
| **Perfil tributario** | Resumen derivado del RUT: régimen, responsabilidades, si retiene, si se le retiene, municipio y CIIU. | — | Validador del paso 3 ("perfil tributario del proveedor nuevo"). |

### Algoritmo del DV del NIT (§8.2)

1. Toma los dígitos del NIT (sin puntos, sin DV) **de derecha a izquierda**.
2. Multiplica cada uno por el peso de su posición: 3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71.
3. Suma los productos y calcula el residuo de dividir entre 11.
4. Si el residuo es 0 o 1, **DV = residuo**; si no, **DV = 11 − residuo**.

Ejemplo (NIT de la DIAN, 800197268): dígitos de derecha a izquierda 8,6,2,7,9,1,0,0,8 →
8·3 + 6·7 + 2·13 + 7·17 + 9·19 + 1·23 + 0·29 + 0·37 + 8·41 = 733; 733 mod 11 = 7; DV = 11 − 7 = **4**
→ 800.197.268-**4**. Buen caso de prueba para el validador.

## 5. IVA

| Término | Definición | Norma | En el sistema |
|---|---|---|---|
| **IVA** (impuesto sobre las ventas) | Impuesto sobre la venta de bienes, prestación de servicios e importaciones, salvo exclusiones. | E.T. art. 420 | `Factura.iva`; coherencia de IVA (paso 3). |
| **Tarifa general** | Tarifa que aplica por defecto; hoy 19 %. Como toda tarifa, se maneja como `⟨parámetro⟩` con vigencia. | E.T. art. 468 | Validador de coherencia de IVA; feature "tarifa efectiva de IVA" (modelo B). |
| **Tarifa diferencial** | Tarifa reducida para bienes y servicios listados; hoy 5 %. `⟨parámetro⟩`. | E.T. arts. 468-1, 468-3 | Ídem. |
| **Exento** | Bien o servicio **gravado a tarifa 0 %**: el productor sí puede descontar el IVA pagado y pedir devolución. | E.T. arts. 477, 481 | En el XML se ve como impuesto con tarifa 0; distinto de excluido. |
| **Excluido** | Bien o servicio **no gravado**: no genera IVA y el IVA pagado en su producción no es descontable (va al costo). | E.T. arts. 424, 476 | En el XML no hay impuesto IVA en la línea, o va como "no causa" `[verificar representación en UBL]`. |
| **IVA descontable** | IVA pagado en compras que el responsable resta del IVA generado en su declaración, si cumple requisitos (soporte válido, relación con operaciones gravadas, plazo). | E.T. arts. 485, 488, 496 | Previsto: informe del cierre. |
| **IVA generado** | IVA que el responsable cobra en sus ventas. | E.T. art. 483 `[verificar]` | — |

## 6. Retenciones

| Término | Definición | Norma | En el sistema |
|---|---|---|---|
| **UVT** (Unidad de Valor Tributario) | Unidad que expresa bases, topes y sanciones tributarias. Su valor en pesos lo fija la DIAN cada año por resolución. **Nunca constante en código.** | E.T. art. 868 | Tabla de parámetros con `vigente_desde` / `vigente_hasta` (regla dura 8). |
| **Retención en la fuente (retefuente)** | Cobro anticipado del impuesto de renta: el pagador (agente de retención) descuenta un porcentaje del pago y lo declara y paga a la DIAN. | E.T. arts. 365–419; DUR | Campo `Factura.retenciones`; nodo `explicar_diferencias` (§11); paso 7. |
| **Concepto de retención** | Categoría del pago (compras, servicios, honorarios, arrendamientos, etc.) que determina **base mínima en UVT** y **tarifa**. Ambas son `⟨parámetro⟩`. | E.T. arts. 392, 401; DUR | Tabla de parámetros por concepto, con vigencia y fuente. |
| **Base mínima** | Monto a partir del cual se practica la retención de un concepto, expresado en UVT. `⟨parámetro⟩`. | DUR | Ídem. |
| **ReteIVA** | Retención de una parte del IVA facturado, practicada por agentes de retención de IVA (p. ej. grandes contribuyentes) sobre responsables de IVA. Porcentaje sobre el IVA = `⟨parámetro⟩`. | E.T. arts. 437-1, 437-2 | Matriz de retenciones; explicación de pago neto. |
| **ReteICA** | Retención del impuesto de industria y comercio, **municipal**: tarifas, bases y agentes los define cada municipio (el caso guía usa Medellín). | Ley 14 de 1983; Decreto 1333 de 1986; acuerdo municipal de Medellín `[verificar acuerdo y decreto vigentes]` | Parámetros por municipio con vigencia; nodo `explicar_diferencias`. |
| **ICA** (industria y comercio) | Impuesto municipal sobre actividades industriales, comerciales y de servicios, con tarifa por CIIU y municipio. | Ley 14 de 1983 | Calendario municipal. |
| **Matriz quién retiene a quién** | Tabla que, según el perfil del pagador y del beneficiario (gran contribuyente, autorretenedor, Simple, responsable o no de IVA, persona natural/jurídica), dice qué retenciones aplican. | Derivada de E.T. arts. 368, 437-2, 911 y normas municipales | Previsto: regla en código validada por el contador asesor; base para calcular el neto a pagar (§6, prueba de dominio). |
| **Neto a pagar** | Total de la factura menos las retenciones practicadas. Es lo que suele aparecer en el extracto. | — | Emparejamiento difuso con "monto ajustado por retenciones" (§11). |
| **Certificado de retención** | Documento que el agente de retención expide al retenido. | E.T. arts. 378, 381 | Fuera de alcance inicial. |

> **Nota sobre retenciones en el XML (riesgo para el validador de totales):** en la factura
> electrónica las retenciones se informan en `WithholdingTaxTotal` y, según el anexo técnico, **no
> se restan** del valor a pagar del documento (`LegalMonetaryTotal/PayableAmount`) `[verificar con el
> anexo 1.9]`. Si el campo `total` se toma de `PayableAmount`, la fórmula
> `subtotal + iva − retenciones = total` de §8.2 fallaría en facturas con retenciones. Hay que definir
> en `GUIA.md` si `total` es el total facturado o el neto a pagar.

## 7. GMF y bancos

| Término | Definición | Norma | En el sistema |
|---|---|---|---|
| **GMF / 4 por mil** | Gravamen a los Movimientos Financieros: impuesto sobre retiros y transacciones financieras; tarifa hoy de cuatro por mil (`⟨parámetro⟩`). Aparece como cargo en el extracto. | E.T. arts. 870–881 (tarifa art. 872) | Movimiento del extracto; categoría de diferencia "4 por mil" (§11). |
| **Cuenta exenta de GMF** | Cuenta marcada por el titular cuyos retiros mensuales están exentos hasta un tope en UVT (`⟨parámetro⟩`). | E.T. art. 879 | Explica extractos sin cargo de GMF. |
| **Extracto bancario** | Reporte del banco con los movimientos de una cuenta en un periodo: fecha, descripción, referencia, débito, crédito, saldo. | — | Esquema `ExtractoBancario` (`movimientos`); 30 docs del corpus; paso 7 (95 movimientos). |
| **Comisión bancaria** | Cobro del banco por servicios (transferencias, manejo, etc.), con su IVA. | — | Categoría de diferencia "comisión". |
| **PSE** | Pagos Seguros en Línea (operado por ACH Colombia): botón de pago desde la cuenta del pagador. Suele dejar una referencia del comercio. | — | Pista para el emparejamiento por referencia. |
| **Transferencia** | Movimiento de fondos entre cuentas, propias o de terceros, del mismo banco o de otro (ACH). | — | Movimientos del extracto. |
| **Referencia** | Texto o número del movimiento (factura, NIT, convenio). Su formato varía por banco. | — | Feature del emparejamiento; dato a normalizar por banco. |

## 8. Contabilidad básica

| Término | Definición | Norma | En el sistema |
|---|---|---|---|
| **Partida doble** | Todo hecho económico se registra con débitos y créditos por el mismo valor. | Marco técnico NIIF (Decreto 2420 de 2015) | Previsto: el nodo `registrar` genera asientos balanceados. |
| **Asiento / comprobante contable** | Registro de un hecho económico con sus cuentas, débitos, créditos y soporte. | Decreto 2420 de 2015 `[verificar artículo]` | Salida de `registrar`; exportación al software contable (paso 9). |
| **Causación (devengo)** | Reconocer ingresos y gastos cuando ocurren, no cuando se cobran o pagan. La compra se registra al recibir la factura. | Marco conceptual NIIF; E.T. art. 28 (ingresos, renta) | La factura causa la CxP; el pago del extracto la cancela (conciliación). |
| **Base de caja** | Registrar solo cuando entra o sale el dinero. Contraste con causación. | — | — |
| **CxP** (cuentas por pagar) | Obligación con proveedores originada en compras causadas y no pagadas. | — | Lo que se concilia contra los débitos del extracto (paso 7). |
| **CxC** (cuentas por cobrar) | Derecho de cobro a clientes por ventas causadas no cobradas. | — | Créditos del extracto (fuera del alcance inicial del caso guía). |
| **NIIF para pymes / microempresas** | Marcos de información financiera aplicables a los grupos 2 y 3. | Ley 1314 de 2009; Decreto 2420 de 2015 (anexos 2 y 3) | Contexto del RAG. |
| **Plan de cuentas / PUC** | Catálogo de cuentas contables. El PUC del Decreto 2650 de 1993 se sigue usando como referencia de codificación, aunque tras la convergencia a NIIF su obligatoriedad cambió `[verificar posición del CTCP]`. | Decreto 2650 de 1993 | Mapeo de cuentas en la exportación (paso 9). |

## 9. Conciliación bancaria

| Término | Definición | Norma | En el sistema |
|---|---|---|---|
| **Conciliación bancaria** | Comparar los registros contables (facturas/CxP) con el extracto para explicar cada diferencia de saldo en un periodo. | — | Grafo LangGraph de §11; paso 7 y 8. |
| **Cruce / emparejamiento** | Asociación entre uno o varios documentos y uno o varios movimientos. | — | `propuestas` del estado del grafo; `proponer_cruce` (solo propone). |
| **Emparejamiento exacto** | Cruce por monto, fecha y referencia idénticos; lo resuelve código (regla dura 7). | — | Nodo `emparejar_exacto`. |
| **Emparejamiento difuso** | Cruce con diferencias explicables (retenciones, comisión, fecha cercana). | — | Nodo `emparejar_difuso`. |
| **Partida conciliatoria** | Diferencia legítima entre libros y extracto: pago registrado aún no debitado (o al revés), cargos del banco no contabilizados (GMF, comisiones), consignaciones en tránsito, errores. | — | Categorías de `explicar_diferencias`; "factura sin pago", "movimiento sin factura". |
| **Pago parcial** | Un movimiento cubre solo una parte de una factura. | — | Escenario de `evals/datasets/conciliacion/`. |
| **Pago agrupado** | Un movimiento paga varias facturas a la vez. | — | Búsqueda de subconjuntos limitados (§11). |
| **Pago neto de retenciones** | El pago es el total menos retefuente, ReteIVA y/o ReteICA. | — | Categoría de diferencia "retenciones". |
| **Diferencia sin explicar** | Diferencia que ninguna regla explica; requiere aprobación individual con comentario. | — | Política de `governance/policies.py` (riesgo alto). |
| **Cierre mensual** | Proceso de dejar el periodo contable completo y conciliado. | — | Meta del caso guía: de 2 días a medio día. |

## 10. Calendario tributario

| Término | Definición | Norma | En el sistema |
|---|---|---|---|
| **Calendario tributario** | Fechas de vencimiento de declaraciones y pagos, fijadas por decreto cada año y escalonadas por el **último (o últimos) dígito(s) del NIT**. | Decreto anual del Gobierno (modifica el DUR) | Tabla de vencimientos con vigencia (regla dura 8); fase 5. |
| **Declaración de retención en la fuente** | Declaración mensual de lo retenido (formulario 350). | E.T. art. 606 | Calendario. |
| **Declaración de IVA** | Bimestral para grandes contribuyentes y quienes superen un tope de ingresos en UVT (`⟨parámetro⟩`); cuatrimestral para los demás (formulario 300). | E.T. art. 600 | Calendario según perfil. |
| **Declaración de renta** | Anual (formulario 110 personas jurídicas; 210 personas naturales). | E.T. arts. 591 y ss. | Calendario. |
| **Información exógena** | Reporte anual a la DIAN de información de terceros (pagos, retenciones, ingresos, saldos) en formatos definidos por resolución anual (p. ej. 1001 pagos, 1007 ingresos `[verificar]`). Responsabilidad 14. | E.T. art. 631; resolución DIAN anual | Previsto: datos de facturas y retenciones alimentan los formatos. |
| **ICA (declaración municipal)** | Declaración del impuesto de industria y comercio con periodicidad y fechas de cada municipio. | Acuerdo municipal `[verificar Medellín]` | Calendario municipal con vigencia. |

## 11. Oficio del contador

| Término | Definición | Norma | En el sistema |
|---|---|---|---|
| **Contador público** | Profesional con tarjeta profesional que da fe pública de los actos de su profesión. | Ley 43 de 1990 | Usuaria principal (Laura, caso guía). |
| **Fe pública** | La firma del contador presume que el acto se ajusta a las normas. Por eso el sistema propone y la persona aprueba. | Ley 43 de 1990, art. 10 | Gobernanza: aprobación humana antes de `registrar`. |
| **Revisor fiscal** | Órgano de fiscalización obligatorio en ciertas sociedades. | C. Co. arts. 203 y ss. | Fuera de alcance. |
| **Junta Central de Contadores (JCC)** | Tribunal disciplinario y registro de la profesión. | Ley 43 de 1990 | — |
| **Multiempresa** | Un contador lleva varias empresas (Laura lleva 8). | — | `organization_id` y RLS en todas las tablas (regla dura 6). |
| **Software contable** | Siigo, Alegra, World Office, Helisa: destino de los registros; cada uno tiene su formato de importación. | — | Exportación (paso 9: "importación sin errores"). |

## 12. Conservación y datos

| Término | Definición | Norma | En el sistema |
|---|---|---|---|
| **Conservación de documentos (comercial)** | Libros y papeles del comerciante se conservan **10 años**. | C. Co. art. 60; Ley 962 de 2005, art. 28 | Política de retención por organización (fase 5). |
| **Conservación (tributaria)** | Soportes de las declaraciones se conservan al menos por el término de firmeza de la declaración. | E.T. art. 632 `[verificar redacción vigente]` | Ídem. |
| **Firmeza de la declaración** | Plazo tras el cual la DIAN ya no puede modificar una declaración; regla general de 3 años, con excepciones (pérdidas, precios de transferencia). | E.T. art. 714 `[verificar plazos de las excepciones]` | Plazo como `⟨parámetro⟩`. |
| **Habeas data / tratamiento de datos personales** | Derecho del titular a conocer, actualizar y suprimir sus datos; quien los trata necesita autorización y una política de tratamiento. | Ley 1581 de 2012; Decreto 1377 de 2013 (compilado en Decreto 1074 de 2015) | Regla dura 1; autorización al registrarse; `ml/anonymize.py`. |
| **Anonimización** | Reemplazo de datos personales (NIT, cédula, celular, cuentas, correos, direcciones) por valores falsos con el mismo formato. | — | `ml/anonymize.py` (§8.1); NIT falso con DV válido. |
| **Dato sintético** | Documento generado (Faker `es_CO`) cuando faltan reales; marcado `synthetic=true`, nunca en test. | — | §8.1. |

---

## Fuentes consultadas (2026-11-03)

- DIAN, retiro de oficio de la responsabilidad 09 de la casilla 53:
  https://www.dian.gov.co/tramitesservicios/Paginas/Retirandoresponsabilidad09retfuenteimpuestosobreventas.aspx
- Normograma DIAN, Resolución 000167 de 2021 (documento soporte):
  https://normograma.dian.gov.co/dian/compilacion/docs/resolucion_dian_0167_2021.htm
- Providencias de la Rama Judicial que citan el art. 2.2.2.53.4 del Decreto 1074 de 2015 (mod.
  Decreto 1154 de 2020) sobre aceptación tácita en tres días hábiles (fuente secundaria):
  https://www.ramajudicial.gov.co/documents/35612220/9fe6f008-da6c-6e3a-8411-0c5b9d40819c
- Secretaría del Senado (Estatuto Tributario): **no respondió** en esta consulta (conexión
  rechazada). Los artículos del E.T. citados quedan por contrastar con el texto oficial.

## Pendiente de validar con el contador asesor

1. **Cuenta de cobro y documento soporte:** criterio para clasificar cuándo una cuenta de cobro obliga
   al comprador a generar documento soporte (paso 6) y la respuesta de referencia del RAG.
2. **Campo `total` vs retenciones:** si `Factura.total` es el valor facturado o el neto a pagar, y la
   fórmula del validador de totales (ver nota de la sección 6).
3. **Matriz quién retiene a quién:** reglas para gran contribuyente, autorretenedor, Simple, no
   responsable de IVA y persona natural; excepciones del art. 911 E.T. para el Simple.
4. **Códigos de la casilla 53:** lista oficial vigente completa (confirmar 42 y 53; manejo del 09
   retirado en RUT antiguos).
5. **ReteICA de Medellín:** acuerdo y decreto vigentes, tarifas por CIIU, quién es agente y bases.
6. **Exento vs excluido en el XML:** cómo se representa cada caso en UBL para que el validador de IVA
   no los confunda.
7. **Códigos de eventos RADIAN** (030–034) y su efecto en la aceptación.
8. **Tope del tiquete POS** y su efecto en la deducibilidad de compras pequeñas.
9. **Plan de cuentas:** si se usa el PUC como codificación de exportación y qué cuentas para compra
   con IVA y retenciones (prueba de dominio de §6).
10. **Plazos de conservación y firmeza** para redactar la política de retención (Preparación, §7
    paso 9), incluidas las excepciones del art. 714 E.T.
11. **NIT de personas naturales:** confirmar longitud admitida, para ajustar la regex del anonimizador
    (§8.1) y el validador de DV.
