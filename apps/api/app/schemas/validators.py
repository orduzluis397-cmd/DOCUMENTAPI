"""Validadores de dominio (INSTRUCCIONES.md §8.2, caso guía §2 paso 3).

Son funciones puras: no lanzan excepciones por datos del documento, devuelven una lista de
``ResultadoValidacion`` para que la revisión humana vea qué falló y por qué. Un campo ausente
(``None``) no se valida: la regla queda fuera de la lista.

Regla de totales de la factura ``[validar con contador asesor]`` (ver ``GUIA.md``): ``total`` es
el valor facturado (``PayableAmount``) y las retenciones **no** entran en la fórmula::

    subtotal - descuentos + cargos + iva + otros_impuestos - anticipos ≈ total   (tolerancia $1)

La fórmula de §8.2 (``subtotal + iva - retenciones = total``) corresponde al neto a pagar, que el
esquema expone como ``Factura.neto_a_pagar``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.catalogos import RESPONSABILIDADES_RUT, ResponsabilidadRUT, buscar_responsabilidad
from app.schemas.contrato import Contrato
from app.schemas.cuenta_cobro import CuentaCobro
from app.schemas.extracto import ExtractoBancario
from app.schemas.factura import Factura
from app.schemas.rut import RUT

TOLERANCIA = Decimal("1")
FECHA_MINIMA = date(2000, 1, 1)
PESOS_DV = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)
_CUFE = re.compile(r"^[0-9a-f]{96}$")
_CERO = Decimal("0")


class ResultadoValidacion(BaseModel):
    model_config = ConfigDict(frozen=True)

    regla: str
    ok: bool
    severidad: Literal["error", "advertencia"] = "error"
    campos: tuple[str, ...]
    mensaje: str


# ------------------------------------------------------------------------------- reglas sueltas


def calcular_dv(nit: str) -> int:
    """DV DIAN: dígitos de derecha a izquierda x 3, 7, 13, …, 71; suma mod 11.

    Residuo 0 o 1 → DV = residuo; si no, DV = 11 - residuo. ``800197268`` → ``4``.
    """
    if not nit.isdigit() or len(nit) > len(PESOS_DV):
        raise ValueError(f"NIT inválido: se esperan de 1 a {len(PESOS_DV)} dígitos sin puntos")
    suma = sum(int(d) * p for d, p in zip(reversed(nit), PESOS_DV, strict=False))
    residuo = suma % 11
    return residuo if residuo in (0, 1) else 11 - residuo


def dv_valido(nit: str, dv: int) -> bool:
    try:
        return calcular_dv(nit) == dv
    except ValueError:
        return False


def cufe_valido(cufe: str) -> bool:
    """CUFE/CUDE: SHA-384 en hexadecimal, 96 caracteres."""
    return bool(_CUFE.match(cufe.strip().lower()))


def montos_cuadran(esperado: Decimal, obtenido: Decimal, tolerancia: Decimal = TOLERANCIA) -> bool:
    return abs(esperado - obtenido) <= tolerancia


def validar_dv(
    nit: str | None, dv: int | None, campo_nit: str, campo_dv: str
) -> list[ResultadoValidacion]:
    if nit is None or dv is None:
        return []
    ok = dv_valido(nit, dv)
    mensaje = (
        "DV correcto" if ok else f"DV {dv} no corresponde al NIT (esperado {calcular_dv(nit)})"
    )
    return [
        ResultadoValidacion(regla="dv_nit", ok=ok, campos=(campo_nit, campo_dv), mensaje=mensaje)
    ]


def validar_fecha(
    fecha: date | None,
    campo: str,
    hoy: date | None = None,
    minima: date = FECHA_MINIMA,
) -> list[ResultadoValidacion]:
    """Fecha no futura y no anterior a ``minima``."""
    if fecha is None:
        return []
    hoy = hoy or date.today()
    if fecha > hoy:
        return [_error("fecha_no_futura", (campo,), f"{fecha.isoformat()} es posterior a hoy")]
    if fecha < minima:
        return [_error("fecha_en_rango", (campo,), f"{fecha.isoformat()} es anterior a {minima}")]
    return [_ok("fecha_en_rango", (campo,))]


def validar_cufe(cufe: str | None, campo: str = "cufe") -> list[ResultadoValidacion]:
    if cufe is None:
        return []
    if cufe_valido(cufe):
        return [_ok("cufe_96_hex", (campo,))]
    return [_error("cufe_96_hex", (campo,), f"se esperan 96 hex, hay {len(cufe)} caracteres")]


# ------------------------------------------------------------------------------- por documento


def total_esperado_factura(f: Factura) -> Decimal | None:
    """``subtotal - descuentos + cargos + iva + otros_impuestos - anticipos`` o ``None``."""
    if f.subtotal is None or f.iva is None:
        return None
    return (
        f.subtotal
        - (f.descuentos or _CERO)
        + (f.cargos or _CERO)
        + f.iva
        + (f.otros_impuestos or _CERO)
        - (f.anticipos or _CERO)
    )


def validar_totales_factura(
    f: Factura, tolerancia: Decimal = TOLERANCIA
) -> list[ResultadoValidacion]:
    resultados: list[ResultadoValidacion] = []
    esperado = total_esperado_factura(f)
    if esperado is not None and f.total is not None:
        campos = (
            "subtotal",
            "descuentos",
            "cargos",
            "iva",
            "otros_impuestos",
            "anticipos",
            "total",
        )
        if montos_cuadran(esperado, f.total, tolerancia):
            resultados.append(_ok("total_factura", campos))
        else:
            resultados.append(
                _error(
                    "total_factura",
                    campos,
                    f"subtotal - descuentos + cargos + impuestos - anticipos = {esperado}, "
                    f"total = {f.total} (diferencia {f.total - esperado})",
                )
            )
    if f.retenciones is not None and f.total is not None and f.retenciones > f.total:
        resultados.append(
            _error("retenciones_menores_al_total", ("retenciones", "total"), "retenciones > total")
        )
    valores = [linea.valor_total for linea in f.lineas]
    if f.subtotal is not None and valores and all(v is not None for v in valores):
        suma = sum((v for v in valores if v is not None), _CERO)
        if montos_cuadran(suma, f.subtotal, tolerancia):
            resultados.append(_ok("suma_lineas", ("lineas", "subtotal")))
        else:
            resultados.append(
                _error(
                    "suma_lineas",
                    ("lineas", "subtotal"),
                    f"líneas = {suma}, subtotal = {f.subtotal}",
                )
            )
    return resultados


def validar_factura(f: Factura, hoy: date | None = None) -> list[ResultadoValidacion]:
    return [
        *validar_dv(f.nit_emisor, f.dv_emisor, "nit_emisor", "dv_emisor"),
        *validar_dv(f.nit_adquirente, f.dv_adquirente, "nit_adquirente", "dv_adquirente"),
        *validar_fecha(f.fecha_emision, "fecha_emision", hoy),
        *validar_cufe(f.cufe),
        *validar_totales_factura(f),
    ]


def validar_cuenta_cobro(c: CuentaCobro, hoy: date | None = None) -> list[ResultadoValidacion]:
    return [
        *validar_dv(c.nit_cobrador, c.dv_cobrador, "nit_cobrador", "dv_cobrador"),
        *validar_dv(c.nit_pagador, c.dv_pagador, "nit_pagador", "dv_pagador"),
        *validar_fecha(c.fecha, "fecha", hoy),
    ]


def validar_responsabilidades(
    codigos: Iterable[str],
    fecha: date | None,
    catalogo: tuple[ResponsabilidadRUT, ...] = RESPONSABILIDADES_RUT,
) -> list[ResultadoValidacion]:
    """Advierte de códigos desconocidos o no vigentes (p. ej. el 09, retirado de oficio)."""
    resultados: list[ResultadoValidacion] = []
    for codigo in codigos:
        r = buscar_responsabilidad(codigo, catalogo)
        if r is None:
            resultados.append(
                _advertencia(
                    "responsabilidad_conocida",
                    ("responsabilidades",),
                    f"código {codigo} no está en el catálogo",
                )
            )
        elif not r.vigente_en(fecha):
            resultados.append(
                _advertencia(
                    "responsabilidad_vigente",
                    ("responsabilidades",),
                    f"código {codigo} ({r.nombre}) no vigente"
                    + (": retirado; RUT posiblemente desactualizado" if r.retirado else ""),
                )
            )
    return resultados


def validar_rut(r: RUT, hoy: date | None = None) -> list[ResultadoValidacion]:
    return [
        *validar_dv(r.nit, r.dv, "nit", "dv"),
        *validar_fecha(r.fecha_generacion, "fecha_generacion", hoy, minima=date(1990, 1, 1)),
        *validar_responsabilidades(r.responsabilidades, r.fecha_generacion),
    ]


def validar_extracto(
    e: ExtractoBancario, hoy: date | None = None, tolerancia: Decimal = TOLERANCIA
) -> list[ResultadoValidacion]:
    resultados = [
        *validar_fecha(e.periodo_inicio, "periodo_inicio", hoy),
        *validar_fecha(e.periodo_fin, "periodo_fin", hoy),
    ]
    if e.periodo_inicio and e.periodo_fin and e.periodo_inicio > e.periodo_fin:
        resultados.append(
            _error("periodo_ordenado", ("periodo_inicio", "periodo_fin"), "inicio posterior al fin")
        )
    if e.periodo_inicio and e.periodo_fin:
        fuera = [
            i
            for i, m in enumerate(e.movimientos)
            if m.fecha is not None and not (e.periodo_inicio <= m.fecha <= e.periodo_fin)
        ]
        if fuera:
            resultados.append(
                _error(
                    "movimientos_en_periodo",
                    ("movimientos",),
                    f"movimientos fuera del periodo: {fuera}",
                )
            )
    valores = [m.valor for m in e.movimientos]
    if (
        e.saldo_inicial is not None
        and e.saldo_final is not None
        and valores
        and all(v is not None for v in valores)
    ):
        esperado = e.saldo_inicial + sum((v for v in valores if v is not None), _CERO)
        campos = ("saldo_inicial", "movimientos", "saldo_final")
        if montos_cuadran(esperado, e.saldo_final, tolerancia):
            resultados.append(_ok("saldo_cuadra", campos))
        else:
            resultados.append(
                _error(
                    "saldo_cuadra",
                    campos,
                    f"saldo inicial + movimientos = {esperado}, saldo final = {e.saldo_final}",
                )
            )
    return resultados


def validar_contrato(c: Contrato, hoy: date | None = None) -> list[ResultadoValidacion]:
    resultados = [*validar_fecha(c.fecha_firma, "fecha_firma", hoy)]
    for i, parte in enumerate(c.partes):
        resultados.extend(validar_dv(parte.nit, parte.dv, f"partes[{i}].nit", f"partes[{i}].dv"))
    if c.fecha_inicio and c.fecha_fin and c.fecha_inicio > c.fecha_fin:
        resultados.append(
            _error("vigencia_ordenada", ("fecha_inicio", "fecha_fin"), "inicio posterior al fin")
        )
    return resultados


def validar_documento(
    doc: Factura | CuentaCobro | RUT | ExtractoBancario | Contrato, hoy: date | None = None
) -> list[ResultadoValidacion]:
    match doc:
        case Factura():
            return validar_factura(doc, hoy)
        case CuentaCobro():
            return validar_cuenta_cobro(doc, hoy)
        case RUT():
            return validar_rut(doc, hoy)
        case ExtractoBancario():
            return validar_extracto(doc, hoy)
        case Contrato():
            return validar_contrato(doc, hoy)


# ------------------------------------------------------------------------------- auxiliares


def _ok(regla: str, campos: tuple[str, ...]) -> ResultadoValidacion:
    return ResultadoValidacion(regla=regla, ok=True, campos=campos, mensaje="ok")


def _error(regla: str, campos: tuple[str, ...], mensaje: str) -> ResultadoValidacion:
    return ResultadoValidacion(regla=regla, ok=False, campos=campos, mensaje=mensaje)


def _advertencia(regla: str, campos: tuple[str, ...], mensaje: str) -> ResultadoValidacion:
    return ResultadoValidacion(
        regla=regla, ok=False, severidad="advertencia", campos=campos, mensaje=mensaje
    )
