# Guía de anotación del conjunto dorado

> **Versión:** 0.1 · 2026-11-03 · estado: borrador. **Mantiene:** agente `datos-corpus`.
> **Revisa:** `experto-contable` y el **contador asesor** (los puntos marcados
> `[validar con contador asesor]` no son definitivos hasta su visto bueno).
> Esquemas de referencia: `apps/api/app/schemas/` (INSTRUCCIONES.md §8.2). Si la guía y el esquema
> discrepan, se corrige uno de los dos en el mismo PR; nunca se anota "a criterio".

## 1. Para qué sirve

Cada documento del conjunto dorado tiene **un JSON con la verdad** de sus campos. La precisión por
campo del extractor se mide comparando contra ese JSON, así que dos anotadores que siguen esta guía
deben producir **el mismo JSON, carácter por carácter**. Si el acuerdo de la doble anotación (20 %)
baja de 95 % en un campo, se corrige esta guía, no al anotador.

## 2. Reglas generales (todos los tipos)

| Regla | Cómo | Ejemplo correcto | Incorrecto |
|---|---|---|---|
| Fechas | ISO 8601 `AAAA-MM-DD`, sin hora. Si el documento trae hora, se descarta. | `"2026-10-15"` | `"15/10/2026"`, `"15 oct 2026"`, `"2026-10-15T08:00"` |
| Montos | Texto decimal con **punto** como separador decimal, **sin separador de miles**, sin `$` ni `COP`, hasta 2 decimales. Se copian los decimales que trae el documento (`119000` o `119000.00` valen igual). | `"119000.00"`, `"4000"` | `"119.000"`, `"$119,000.00"`, `"119.000,00"`, `119000.0` (número JSON) |
| Signo | Solo los movimientos del extracto llevan signo (sección 7). El resto de montos es ≥ 0. | `"-4000.00"` en un débito | `"-2500"` en `retenciones` |
| NIT / cédula | Solo dígitos, **sin puntos, sin espacios y sin DV**. El DV va en su campo `dv_*` como número. Persona natural: el NIT es la cédula (longitud variable, de 5 a 10 dígitos en la práctica). | `"nit_emisor": "900123456", "dv_emisor": 8` | `"900.123.456-8"`, `"900123456-8"`, `"9001234568"` |
| DV | Se anota **el que aparece en el documento**, aunque esté mal: el validador es quien detecta el error. Si no aparece, `null` (no se calcula). | `"dv_cobrador": null` | DV calculado a mano |
| Ausente | Si el dato no aparece en el documento: `null`. Nunca `""`, `"N/A"`, `0` ni un valor inferido. Listas sin elementos: `[]`. | `"descuentos": null` | `"descuentos": "0"` cuando la factura no muestra descuentos |
| Ilegible | Igual que ausente (`null`) y se deja una nota en Label Studio con la razón. | `null` + nota | Adivinar |
| Textos | Tal como aparecen (mayúsculas, tildes y puntuación del documento), con espacios internos colapsados a uno y sin espacios al inicio o final. No se corrigen errores ortográficos. | `"FERRETERIA EL TORNILLO S.A.S."` | `"Ferretería El Tornillo SAS"` si el documento dice otra cosa |
| Códigos | Como texto con sus ceros a la izquierda. | `"05"`, `"4752"` | `5`, `"5"` |
| Datos personales | El corpus ya está anonimizado (`ml/anonymize.py`): se anotan los **valores falsos** tal como aparecen. Si se ve un dato real sin anonimizar, **se detiene la anotación** y se reporta (regla dura 1). | | Anotar el dato real |

## 3. Formato del archivo

Un archivo por documento en `evals/datasets/golden/<split>/<doc_id>.json` (`split` = `dev`, `val`
o `test`; `test` congelado). El envoltorio queda así (se cierra en F0-07):

```json
{
  "doc_id": "fac-0001",
  "synthetic": false,
  "fuente_verdad": "xml",
  "version_guia": "0.1",
  "documento": { "tipo_documento": "factura", "...": "campos de las secciones 4 a 8" }
}
```

- `fuente_verdad`: `"xml"` (facturas: generado por el parser determinista y revisado) o
  `"anotacion"` (Label Studio).
- `synthetic`: `true` para documentos generados con Faker; nunca van a `test`.
- `documento` debe validar con `app.schemas.documento_adapter` (campos desconocidos = error).

## 4. Factura electrónica (`tipo_documento: "factura"`)

La verdad sale del **XML** (no de la representación gráfica). En un `AttachedDocument`, se toma la
factura embebida en `cac:Attachment/cac:ExternalReference/cbc:Description`.

### 4.1 Definición de `total` `[validar con contador asesor]`

**Decisión:** `total` es el **valor facturado**, `cac:LegalMonetaryTotal/cbc:PayableAmount`. Las
retenciones se informan aparte en `cac:WithholdingTaxTotal` y **no se restan** del total (según el
anexo técnico, `[verificar con el anexo 1.9]`; ver `docs/glosario.md` §6).

- El **neto a pagar** (`total − retenciones`, lo que suele llegar al banco) **no se anota**: el
  esquema lo deriva como `Factura.neto_a_pagar`.
- Regla del validador (tolerancia $1):
  `subtotal − descuentos + cargos + iva + otros_impuestos − anticipos = total`.
  Un componente `null` cuenta como 0, salvo `subtotal`, `iva` y `total`: si falta alguno, la regla
  no se evalúa.
- Diferencia con INSTRUCCIONES.md §8.2: allí la fórmula es `subtotal + iva − retenciones = total`,
  que corresponde al neto a pagar. Si el contador asesor decide que `total` debe ser el neto, se
  cambian a la vez esta guía, `Factura` y `validar_totales_factura`.

### 4.2 Campos

| Campo | Qué anotar | Origen en UBL 2.1 |
|---|---|---|
| `numero` | Prefijo + consecutivo, sin espacios. | `cbc:ID` |
| `cufe` | 96 caracteres hex en minúsculas. | `cbc:UUID` (`schemeName="CUFE-SHA384"`) |
| `fecha_emision` | Fecha de emisión. | `cbc:IssueDate` |
| `nit_emisor`, `dv_emisor` | NIT sin DV y DV del facturador. | `AccountingSupplierParty//cac:PartyTaxScheme/cbc:CompanyID` y su atributo `schemeID` |
| `razon_social_emisor` | Razón social o nombre del facturador. | `AccountingSupplierParty//cbc:RegistrationName` |
| `nit_adquirente`, `dv_adquirente` | Igual que el emisor, para el comprador. Persona natural con cédula (`schemeName="13"`): `dv_adquirente` = `null` si no aparece. | `AccountingCustomerParty//cbc:CompanyID` |
| `razon_social_adquirente` | Nombre o razón social del comprador. | `AccountingCustomerParty//cbc:RegistrationName` |
| `subtotal` | Antes de impuestos. | `LegalMonetaryTotal/cbc:LineExtensionAmount` |
| `descuentos` | Descuentos globales. `null` si el elemento no existe; `"0.00"` si existe con 0. | `LegalMonetaryTotal/cbc:AllowanceTotalAmount` |
| `cargos` | Cargos globales (misma regla). | `LegalMonetaryTotal/cbc:ChargeTotalAmount` |
| `iva` | Suma de `cac:TaxTotal/cbc:TaxAmount` cuyo esquema es IVA (`cac:TaxScheme/cbc:ID` = `01`). `"0.00"` si la factura declara IVA 0. | `cac:TaxTotal` |
| `otros_impuestos` | Suma de los demás `cac:TaxTotal` (INC `04`, ICA `03`, etc.); `null` si no hay. | `cac:TaxTotal` |
| `anticipos` | Anticipos aplicados. | `LegalMonetaryTotal/cbc:PrepaidAmount` |
| `retenciones` | Suma de todos los `cac:WithholdingTaxTotal/cbc:TaxAmount` (ReteFuente, ReteIVA, ReteICA); `null` si no hay. | `cac:WithholdingTaxTotal` |
| `total` | Valor facturado (4.1). | `LegalMonetaryTotal/cbc:PayableAmount` |
| `lineas` | Una entrada por `cac:InvoiceLine`, en el orden del XML. | `cac:InvoiceLine` |

Campos de cada línea:

| Campo | Qué anotar | Origen |
|---|---|---|
| `descripcion` | Descripción del ítem tal cual. | `cac:Item/cbc:Description` |
| `cantidad` | Decimal sin miles (hasta 6 decimales). | `cbc:InvoicedQuantity` |
| `valor_unitario` | Precio unitario sin IVA (hasta 6 decimales). | `cac:Price/cbc:PriceAmount` |
| `valor_total` | Valor de la línea sin IVA. | `cbc:LineExtensionAmount` de la línea |
| `tarifa_iva` | Porcentaje (`"19"`, `"5"`, `"0"`); `null` si la línea no tiene IVA (excluida). | `cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:Percent` |
| `iva` | IVA de la línea. | `cac:TaxTotal/cbc:TaxAmount` de la línea |

Exento vs. excluido en el XML: pendiente `[validar con contador asesor]` (glosario, punto 6). Mientras
tanto, `tarifa_iva: "0"` si el XML declara la tarifa 0 y `null` si no hay `TaxTotal` en la línea.

## 5. Cuenta de cobro (`tipo_documento: "cuenta_cobro"`)

| Campo | Qué anotar |
|---|---|
| `numero` | Número o consecutivo si aparece; si no, `null`. |
| `fecha` | Fecha de expedición de la cuenta (no la del servicio). |
| `ciudad` | Ciudad donde se expide, tal cual. |
| `nombre_cobrador`, `nit_cobrador`, `dv_cobrador` | Quien cobra (normalmente persona natural: `nit_cobrador` = cédula; `dv_cobrador` solo si aparece). |
| `nombre_pagador`, `nit_pagador`, `dv_pagador` | A quién se le cobra ("DEBE A" / "a favor de"). |
| `concepto` | Concepto o descripción del servicio, texto completo. |
| `valor` | Valor total cobrado en números. Si el valor en letras y en números difieren, se anota el de números y se deja nota. |
| `declara_no_responsable_iva` | `true` si el texto declara que el cobrador **no** es responsable de IVA (o no está obligado a facturar); `false` si declara lo contrario; `null` si no dice nada. |

## 6. RUT (`tipo_documento: "rut"`)

| Campo | Qué anotar | Casilla del formulario 001 `[verificar numeración]` |
|---|---|---|
| `nit`, `dv` | NIT sin DV y DV. | 5 y 6 |
| `tipo_contribuyente` | `"persona_natural"` o `"persona_juridica"`. | 24 |
| `razon_social` | Jurídica: razón social. Natural: apellidos y nombres en el orden del formulario, separados por un espacio. | 31–35 |
| `nombre_comercial` | Si aparece. | 36 |
| `municipio`, `departamento` | Del domicilio principal, tal cual. | 39–40 |
| `direccion_seccional` | Seccional de la DIAN, tal cual. | 12 |
| `actividad_principal` | Código CIIU de 4 dígitos. | 46 |
| `actividades_secundarias` | Lista de códigos CIIU en el orden del formulario. | 48 y siguientes |
| `responsabilidades` | **Todos** los códigos de la casilla 53, como texto de 2 dígitos, en el orden del formulario, aunque alguno ya no esté vigente (p. ej. `"09"`, retirado de oficio). El validador decide la vigencia con el catálogo; el anotador no filtra. | 53 |
| `fecha_generacion` | Fecha de generación del documento. | pie del formulario |

## 7. Extracto bancario (`tipo_documento: "extracto"`)

| Campo | Qué anotar |
|---|---|
| `banco` | Nombre del banco, tal cual. |
| `numero_cuenta` | Como aparece, incluidos los asteriscos si viene enmascarado. |
| `tipo_cuenta` | `"ahorros"` o `"corriente"`. |
| `titular`, `nit_titular` | Titular de la cuenta. |
| `periodo_inicio`, `periodo_fin` | Fechas del periodo del extracto. |
| `saldo_inicial`, `saldo_final` | Con signo si el extracto lo muestra negativo (sobregiro). |
| `total_creditos`, `total_debitos` | Totales del resumen si aparecen, ambos en valor absoluto. |
| `movimientos` | Una entrada por línea del extracto, en orden. |

Movimiento:

| Campo | Qué anotar |
|---|---|
| `fecha` | Fecha del movimiento. Si el extracto solo trae día y mes, el año se toma del periodo. |
| `descripcion` | Texto de la línea tal cual (p. ej. `"GMF 4X1000"`, `"PAGO PSE ..."`). |
| `referencia` | Referencia o número de documento, si hay columna propia; si no, `null`. |
| `valor` | **Con signo:** positivo = crédito (entra dinero), negativo = débito (sale). El GMF y las comisiones son negativos. |
| `saldo` | Saldo después del movimiento, si la línea lo trae. |

## 8. Contrato (`tipo_documento: "contrato"`)

| Campo | Qué anotar |
|---|---|
| `partes` | Una entrada por parte, en el orden en que aparecen: `rol` (`"contratante"` o `"contratista"`), `nombre`, `nit`, `dv`, `representante_legal` (si es persona jurídica). |
| `objeto` | Texto de la cláusula de objeto, completo. |
| `valor` | Valor total del contrato. Si solo hay valor mensual o es indeterminado: `null` y el detalle en `forma_pago`. |
| `forma_pago` | Texto de la cláusula de forma de pago. |
| `fecha_firma` | Fecha de suscripción. |
| `fecha_inicio`, `fecha_fin` | Vigencia. `fecha_fin` puede ser futura. |
| `duracion` | Solo si no hay `fecha_fin`: duración tal como aparece (`"6 meses"`). |

## 9. Casos dudosos frecuentes

- **Dos valores para el mismo campo** (p. ej. total en números y en letras distintos): se anota el
  de números y se deja nota.
- **Nota crédito o débito:** no es `factura`; se aparta del conjunto hasta definir su esquema.
- **Factura sin XML** (solo PDF): se anota desde el PDF con `fuente_verdad: "anotacion"` y nota.
- **Tiquete POS / documento equivalente:** fuera del alcance de la Fase 0; se reporta.

## 10. Pendiente de validar con el contador asesor

1. `total` como valor facturado (`PayableAmount`) y la fórmula del validador (4.1).
2. Representación de exento vs. excluido en `tarifa_iva` (sección 4.2).
3. Lista oficial vigente de la casilla 53 y fecha de retiro del código 09 (`app/schemas/catalogos.py`).
4. Numeración de casillas del formulario 001 citada en la sección 6.
