> **Borrador. Debe revisarlo un abogado antes de usarlo.**

# Política de tratamiento de datos personales · Contable IA

Versión 0.1 · Fecha de entrada en vigencia: `[FECHA]`

**Base normativa:** Ley Estatutaria 1581 de 2012 y Decreto 1377 de 2013 (compilado en el Decreto
Único Reglamentario 1074 de 2015).

## 1. Responsable

`[NOMBRE DEL RESPONSABLE]` · Identificación: `[CC/NIT]` · Domicilio: `[CIUDAD, DIRECCIÓN]` ·
Correo para asuntos de datos personales: `[CORREO]`.

En el **corpus de investigación** (documentos prestados con autorización), Contable IA actúa como
responsable. Cuando una **empresa usuaria** carga sus propios documentos en la aplicación, esa
empresa es responsable de los datos de sus terceros y Contable IA actúa como **encargado** del
tratamiento por cuenta de ella.

## 2. Datos que tratamos

- **Del titular que presta o carga documentos:** nombre o razón social, NIT o cédula, correo,
  teléfono, cargo.
- **Contenidos en los documentos contables** (facturas electrónicas, cuentas de cobro, RUT, extractos
  bancarios, contratos): datos de **terceros** como clientes, proveedores, contratistas y empleados
  (nombres, NIT o cédula, direcciones, teléfonos, correos, números de cuenta, valores y movimientos).
- **De uso de la aplicación:** registros de actividad, correcciones y calificaciones de resultados.

No buscamos tratar datos sensibles ni datos de niños, niñas y adolescentes. Si aparecen en un
documento, se eliminan en la anonimización y no se usan para ninguna finalidad.

## 3. Finalidades

1. Procesar documentos contables para **extraer** sus datos, **validarlos** y **conciliarlos** con
   movimientos bancarios, y prestar el servicio a la empresa usuaria.
2. **Investigar y evaluar** el sistema (medir precisión, construir conjuntos de evaluación, mejorar
   modelos), siempre con **datos anonimizados**.
3. Atender consultas, reclamos y solicitudes de los titulares, y cumplir obligaciones legales.

Los datos no se venden ni se usan para publicidad.

## 4. Anonimización y seguridad

- Los documentos originales se guardan solo en un almacenamiento restringido (`data/` en el entorno
  de trabajo, o el almacenamiento cifrado de la organización en la aplicación).
- **Antes de cualquier uso fuera de ese almacenamiento** —enviarlos a una API externa (proveedores de
  modelos de lenguaje), incorporarlos al repositorio de código, a conjuntos de evaluación o a
  publicaciones— se **anonimizan**: los nombres, NIT, cédulas, teléfonos, correos, direcciones y
  cuentas se reemplazan por valores ficticios con el mismo formato, y se revisa manualmente el
  resultado. La tabla de correspondencias se guarda cifrada y solo en local.
- Ningún documento se publica sin anonimizar. Controles de acceso por organización, cifrado en
  tránsito y en reposo, registros sin datos personales y auditoría de accesos.

## 5. Derechos del titular

Como titular puede: **conocer** los datos que tenemos sobre usted; **actualizarlos** y
**rectificarlos**; pedir prueba de la autorización; ser informado del uso que se les ha dado;
**revocar** la autorización y pedir la **supresión** de sus datos cuando no exista un deber legal o
contractual de conservarlos; presentar quejas ante la Superintendencia de Industria y Comercio
después de agotar el trámite ante nosotros; y acceder gratuitamente a sus datos.

## 6. Procedimiento para consultas y reclamos

Escriba a `[CORREO]` indicando nombre, identificación, la solicitud y un medio de respuesta. Quien
actúe en nombre del titular debe acreditar su representación.

| Trámite | Plazo de respuesta | Prórroga | Norma |
|---------|--------------------|----------|-------|
| **Consulta** (conocer qué datos tenemos y cómo se usan) | 10 días hábiles desde el recibo | Hasta 5 días hábiles más, informando los motivos | Ley 1581 de 2012, art. 14 |
| **Reclamo** (actualizar, rectificar, suprimir, revocar o denunciar un incumplimiento) | 15 días hábiles desde el día siguiente al recibo | Hasta 8 días hábiles más, informando los motivos | Ley 1581 de 2012, art. 15 |

Si el reclamo está incompleto, se pedirá completarlo dentro de los 5 días siguientes; si pasan dos
meses sin respuesta, se entenderá que se desistió. Mientras se tramita, el dato se marca como
"reclamo en trámite". Una revocación o supresión aceptada implica el borrado de los documentos
originales, sus versiones anonimizadas vinculables, los vectores derivados y las trazas asociadas.

## 7. Conservación

| Información | Plazo |
|-------------|-------|
| Documentos originales del corpus de investigación | Hasta `[N]` meses después del fin del proyecto, o hasta la revocación |
| Documentos de una organización usuaria en la aplicación | Mientras la cuenta esté activa y hasta `[N]` días después de su cierre o de la solicitud de borrado |
| Versiones anonimizadas y métricas agregadas | Mientras sean útiles para la evaluación del sistema |
| Prueba de la autorización y registro de solicitudes | Mientras exista el tratamiento y el tiempo necesario para atender reclamos o requerimientos |

La obligación legal de conservar libros y soportes contables y tributarios es de la empresa usuaria,
no de Contable IA; la aplicación permite exportar todo antes de un borrado. Un proceso programado
elimina lo vencido.

## 8. Transmisión y transferencia internacional

Para prestar el servicio usamos proveedores ubicados fuera de Colombia: **proveedores de modelos de
lenguaje** (`[PROVEEDOR LLM 1]`, `[PROVEEDOR LLM 2]`) y **nube y observabilidad**
(`[PROVEEDOR DE NUBE]`, `[PROVEEDOR DE TRAZAS]`), en `[PAÍSES]`. Estos proveedores actúan como
encargados, bajo contrato que les impide usar los datos para fines propios. A los proveedores de
modelos de lenguaje solo se envía **contenido anonimizado** y, cuando el proveedor lo permite, con
retención de datos desactivada. Las transferencias y transmisiones se harán conforme a la Ley 1581 de
2012 y su reglamentación, a países con nivel adecuado de protección según la Superintendencia de
Industria y Comercio o con las garantías contractuales que la norma exige.

## 9. Vigencia y cambios

Esta política rige desde `[FECHA]` y mientras exista el tratamiento. Los cambios sustanciales se
informarán a los titulares por `[MEDIO]` antes de aplicarse y, si cambian las finalidades, se pedirá
una nueva autorización.
