"""Validadores de dominio (§8.2) con casos válidos e inválidos."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.schemas import RUT, Contrato, CuentaCobro, ExtractoBancario, Factura
from app.schemas.validators import (
    ResultadoValidacion,
    calcular_dv,
    cufe_valido,
    dv_valido,
    total_esperado_factura,
    validar_documento,
    validar_factura,
    validar_fecha,
    validar_rut,
)

HOY = date(2026, 11, 3)


def fallidas(resultados: list[ResultadoValidacion]) -> set[str]:
    return {r.regla for r in resultados if not r.ok}


def factura(**cambios: Any) -> Factura:
    datos: dict[str, Any] = {
        "cufe": "ab12" * 24,
        "fecha_emision": "2026-10-15",
        "nit_emisor": "900123456",
        "dv_emisor": 8,
        "nit_adquirente": "800197268",
        "dv_adquirente": 4,
        "subtotal": "100000.00",
        "iva": "19000.00",
        "retenciones": "2500.00",
        "total": "119000.00",
        "lineas": [{"valor_total": "60000.00"}, {"valor_total": "40000.00"}],
    }
    datos.update(cambios)
    return Factura.model_validate(datos)


# ------------------------------------------------------------------ DV


@pytest.mark.parametrize(
    ("nit", "dv"),
    [
        ("800197268", 4),  # caso de §8.2 / glosario (DIAN)
        ("900123456", 8),
        ("860034313", 7),
        ("1020304050", 8),  # persona natural: cédula de 10 dígitos
        ("79123456", 0),  # persona natural: cédula de 8 dígitos
    ],
)
def test_calcular_dv(nit: str, dv: int) -> None:
    assert calcular_dv(nit) == dv
    assert dv_valido(nit, dv)
    assert not dv_valido(nit, (dv + 1) % 10)


@pytest.mark.parametrize("nit", ["", "900.123.456", "1" * 16])
def test_calcular_dv_rechaza_formato(nit: str) -> None:
    with pytest.raises(ValueError, match="NIT inválido"):
        calcular_dv(nit)
    assert not dv_valido(nit, 0)


# ------------------------------------------------------------------ fechas y CUFE


def test_fecha_no_futura_y_en_rango() -> None:
    assert fallidas(validar_fecha(date(2026, 11, 3), "f", HOY)) == set()
    assert fallidas(validar_fecha(date(2026, 11, 4), "f", HOY)) == {"fecha_no_futura"}
    assert fallidas(validar_fecha(date(1999, 12, 31), "f", HOY)) == {"fecha_en_rango"}
    assert validar_fecha(None, "f", HOY) == []


@pytest.mark.parametrize(
    ("cufe", "ok"),
    [
        ("ab12" * 24, True),
        ("AB12" * 24, True),
        ("ab12" * 23, False),  # 92
        ("ab12" * 24 + "a", False),  # 97
        ("zz12" * 24, False),  # no hex
    ],
)
def test_cufe(cufe: str, ok: bool) -> None:
    assert cufe_valido(cufe) is ok


# ------------------------------------------------------------------ factura


def test_factura_valida_sin_fallas() -> None:
    resultados = validar_factura(factura(), HOY)
    assert fallidas(resultados) == set()
    assert {"dv_nit", "fecha_en_rango", "cufe_96_hex", "total_factura", "suma_lineas"} <= {
        r.regla for r in resultados
    }


def test_total_es_valor_facturado_sin_restar_retenciones() -> None:
    # total = PayableAmount: las retenciones no entran en la fórmula (GUIA.md)
    f = factura()
    assert total_esperado_factura(f) == Decimal("119000.00")
    assert f.neto_a_pagar == Decimal("116500.00")
    # Si alguien anota el neto como total, el validador lo marca.
    assert "total_factura" in fallidas(validar_factura(factura(total="116500.00"), HOY))


def test_total_con_tolerancia_de_un_peso() -> None:
    assert "total_factura" not in fallidas(validar_factura(factura(total="119001.00"), HOY))
    assert "total_factura" not in fallidas(validar_factura(factura(total="118999.00"), HOY))
    assert "total_factura" in fallidas(validar_factura(factura(total="119001.01"), HOY))


def test_total_con_descuentos_cargos_anticipos_e_impuestos() -> None:
    f = factura(
        descuentos="5000.00",
        cargos="1000.00",
        otros_impuestos="800.00",
        anticipos="10000.00",
        total="105800.00",
    )
    assert fallidas(validar_factura(f, HOY)) == set()


def test_factura_invalida_marca_cada_regla() -> None:
    f = factura(
        dv_emisor=9,
        fecha_emision="2026-12-01",
        cufe="abc",
        total="150000.00",
        lineas=[{"valor_total": "10.00"}],
    )
    assert fallidas(validar_factura(f, HOY)) == {
        "dv_nit",
        "fecha_no_futura",
        "cufe_96_hex",
        "total_factura",
        "suma_lineas",
    }


def test_retenciones_mayores_al_total() -> None:
    f = factura(retenciones="200000.00")
    assert "retenciones_menores_al_total" in fallidas(validar_factura(f, HOY))


def test_campos_ausentes_no_se_validan() -> None:
    f = Factura.model_validate({"subtotal": "100.00"})
    assert validar_factura(f, HOY) == []


# ------------------------------------------------------------------ otros documentos


def test_rut_codigo_09_retirado_es_advertencia() -> None:
    r = RUT.model_validate(
        {
            "nit": "900123456",
            "dv": 8,
            "responsabilidades": ["05", "09", "48", "99"],
            "fecha_generacion": "2026-01-10",
        }
    )
    resultados = validar_rut(r, HOY)
    malas = [x for x in resultados if not x.ok]
    assert {x.regla for x in malas} == {"responsabilidad_vigente", "responsabilidad_conocida"}
    assert all(x.severidad == "advertencia" for x in malas)
    assert any("09" in x.mensaje for x in malas)


def test_cuenta_cobro_persona_natural() -> None:
    c = CuentaCobro.model_validate(
        {"nit_cobrador": "79123456", "dv_cobrador": 0, "fecha": "2026-10-01", "valor": "500000"}
    )
    assert fallidas(validar_documento(c, HOY)) == set()
    c_mal = CuentaCobro.model_validate({"nit_cobrador": "79123456", "dv_cobrador": 3})
    assert fallidas(validar_documento(c_mal, HOY)) == {"dv_nit"}


def test_extracto_saldo_y_periodo() -> None:
    base: dict[str, Any] = {
        "periodo_inicio": "2026-10-01",
        "periodo_fin": "2026-10-31",
        "saldo_inicial": "1000000.00",
        "saldo_final": "1112500.00",
        "movimientos": [
            {"fecha": "2026-10-05", "valor": "116500.00"},
            {"fecha": "2026-10-06", "valor": "-4000.00"},
        ],
    }
    assert fallidas(validar_documento(ExtractoBancario.model_validate(base), HOY)) == set()
    malo = {**base, "saldo_final": "1200000.00"}
    malo["movimientos"] = [*base["movimientos"], {"fecha": "2026-11-01", "valor": "0"}]
    assert fallidas(validar_documento(ExtractoBancario.model_validate(malo), HOY)) == {
        "saldo_cuadra",
        "movimientos_en_periodo",
    }


def test_contrato_vigencia_y_partes() -> None:
    c = Contrato.model_validate(
        {
            "partes": [
                {"rol": "contratante", "nit": "900123456", "dv": 8},
                {"rol": "contratista", "nit": "79123456", "dv": 5},
            ],
            "fecha_firma": "2026-09-01",
            "fecha_inicio": "2026-09-01",
            "fecha_fin": "2027-02-28",  # la vigencia puede terminar en el futuro
        }
    )
    resultados = validar_documento(c, HOY)
    assert fallidas(resultados) == {"dv_nit"}
    assert any("partes[1]" in campo for r in resultados if not r.ok for campo in r.campos)
    invertido = c.model_copy(update={"fecha_inicio": date(2027, 3, 1)})
    assert "vigencia_ordenada" in fallidas(validar_documento(invertido, HOY))
