"""Esquemas Pydantic de §8.2: normalización en la frontera y ausente = None."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas import (
    RUT,
    Contrato,
    CuentaCobro,
    ExtractoBancario,
    Factura,
    documento_adapter,
)
from app.schemas.catalogos import RESPONSABILIDADES_RUT, buscar_responsabilidad


def factura_valida(**cambios: Any) -> dict[str, Any]:
    datos: dict[str, Any] = {
        "tipo_documento": "factura",
        "numero": "SETP990000001",
        "cufe": "ab12" * 24,
        "fecha_emision": "2026-10-15",
        "nit_emisor": "900123456",
        "dv_emisor": 8,
        "razon_social_emisor": "Ferretería Sintética S.A.S.",
        "nit_adquirente": "1020304050",
        "dv_adquirente": 8,
        "subtotal": "100000.00",
        "iva": "19000.00",
        "retenciones": "2500.00",
        "total": "119000.00",
        "lineas": [
            {
                "descripcion": "Tornillos",
                "cantidad": "100",
                "valor_unitario": "1000",
                "valor_total": "100000.00",
                "tarifa_iva": "19",
                "iva": "19000.00",
            }
        ],
    }
    datos.update(cambios)
    return datos


def test_factura_montos_decimal_y_fecha_iso() -> None:
    f = Factura.model_validate(factura_valida())
    assert f.total == Decimal("119000.00")
    assert isinstance(f.subtotal, Decimal)
    assert f.fecha_emision == date(2026, 10, 15)
    assert f.neto_a_pagar == Decimal("116500.00")


def test_factura_json_ida_y_vuelta() -> None:
    f = Factura.model_validate(factura_valida())
    datos = f.model_dump(mode="json")
    assert datos["total"] == "119000.00"  # Decimal se serializa como texto, sin pérdida
    assert "neto_a_pagar" not in datos  # derivado: no se anota
    assert Factura.model_validate(datos) == f


def test_ausente_es_none() -> None:
    f = Factura.model_validate({"tipo_documento": "factura"})
    assert f.cufe is None
    assert f.total is None
    assert f.lineas == []
    assert f.neto_a_pagar is None


@pytest.mark.parametrize("monto", ["119.000", "119,000.00", "1.234.567", "119000,00", "1e3", "abc"])
def test_monto_rechaza_separadores_y_formatos_ambiguos(monto: str) -> None:
    with pytest.raises(ValidationError):
        Factura.model_validate(factura_valida(total=monto))


@pytest.mark.parametrize(
    ("monto", "esperado"), [(119000, "119000"), (1.5, "1.5"), ("0.10", "0.10")]
)
def test_monto_acepta_numeros(monto: object, esperado: str) -> None:
    assert Factura.model_validate(factura_valida(total=monto)).total == Decimal(esperado)


def test_monto_rechaza_mas_de_dos_decimales_y_negativos() -> None:
    with pytest.raises(ValidationError):
        Factura.model_validate(factura_valida(total="10.555"))
    with pytest.raises(ValidationError):
        Factura.model_validate(factura_valida(total="-5"))


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [("900.123.456", "900123456"), (" 79123456 ", "79123456"), (1020304050, "1020304050")],
)
def test_nit_se_normaliza(entrada: object, esperado: str) -> None:
    assert Factura.model_validate(factura_valida(nit_emisor=entrada)).nit_emisor == esperado


@pytest.mark.parametrize("nit", ["900123456-8", "0123456", "12a45", "1234"])
def test_nit_invalido(nit: str) -> None:
    with pytest.raises(ValidationError):
        Factura.model_validate(factura_valida(nit_emisor=nit))


def test_dv_fuera_de_rango() -> None:
    with pytest.raises(ValidationError):
        Factura.model_validate(factura_valida(dv_emisor=10))


def test_cufe_se_normaliza_a_minusculas() -> None:
    f = Factura.model_validate(factura_valida(cufe=" " + "AB12" * 24 + " "))
    assert f.cufe == "ab12" * 24


def test_campo_desconocido_se_rechaza() -> None:
    with pytest.raises(ValidationError):
        Factura.model_validate(factura_valida(valor_total_factura="1"))


def test_union_discriminada() -> None:
    docs = [
        factura_valida(),
        {"tipo_documento": "cuenta_cobro", "valor": "500000", "nit_cobrador": "52345678"},
        {"tipo_documento": "rut", "nit": "900123456", "dv": 8, "responsabilidades": ["05", 9]},
        {"tipo_documento": "extracto", "movimientos": [{"valor": "-4000.00"}]},
        {"tipo_documento": "contrato", "partes": [{"rol": "contratista", "nit": "79123456"}]},
    ]
    tipos = [type(documento_adapter.validate_python(d)) for d in docs]
    assert tipos == [Factura, CuentaCobro, RUT, ExtractoBancario, Contrato]


def test_rut_responsabilidades_no_es_enum_cerrado() -> None:
    # 09 (retirado) y un código que aún no está en el catálogo se aceptan: lo juzga el validador.
    r = RUT.model_validate({"responsabilidades": ["05", "9", 99], "actividad_principal": "4752"})
    assert r.responsabilidades == ["05", "09", "99"]
    with pytest.raises(ValidationError):
        RUT.model_validate({"responsabilidades": ["5a"]})
    with pytest.raises(ValidationError):
        RUT.model_validate({"actividad_principal": "47"})


def test_catalogo_responsabilidades_con_vigencia() -> None:
    codigos = [r.codigo for r in RESPONSABILIDADES_RUT]
    assert len(codigos) == len(set(codigos))
    nueve = buscar_responsabilidad("09")
    assert nueve is not None
    assert nueve.retirado
    assert not nueve.vigente_en(date(2026, 1, 1))
    cuarenta_ocho = buscar_responsabilidad("48")
    assert cuarenta_ocho is not None
    assert cuarenta_ocho.vigente_en(date(2026, 1, 1))


def test_extracto_movimientos_con_signo() -> None:
    e = ExtractoBancario.model_validate(
        {"movimientos": [{"valor": "-4000.00"}, {"valor": "116500.00"}]}
    )
    assert [m.valor for m in e.movimientos] == [Decimal("-4000.00"), Decimal("116500.00")]
