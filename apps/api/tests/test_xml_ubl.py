"""Parser determinista UBL 2.1 (sin LLM), campo por campo, con fixtures sintéticos."""

from datetime import date
from decimal import Decimal

import pytest

from app.extraction.types import ExtractionError
from app.extraction.xml_ubl import parse_ubl
from app.schemas.validators import validar_factura
from tests.docs_fixtures import (
    CUFE,
    DV_ADQ,
    DV_EMISOR,
    HOY,
    NIT_ADQ,
    NIT_EMISOR,
    attached_document,
    invoice_xml,
    invoice_zip,
)


def _check_invoice_fields(data: bytes) -> None:
    ubl = parse_ubl(data)
    f = ubl.factura
    assert ubl.kind == "factura"
    assert ubl.invalid == {}
    assert f.numero == "SETP990000001"
    assert f.cufe == CUFE
    assert f.fecha_emision == date(2026, 10, 15)
    assert f.nit_emisor == NIT_EMISOR
    assert f.dv_emisor == DV_EMISOR
    # Espacios internos colapsados (GUIA.md §2).
    assert f.razon_social_emisor == "FERRETERIA EL TORNILLO S.A.S."
    assert f.nit_adquirente == NIT_ADQ
    assert f.dv_adquirente == DV_ADQ
    assert f.razon_social_adquirente == "COMERCIALIZADORA ÑANDÚ LTDA"
    assert f.subtotal == Decimal("120000.00")
    assert f.descuentos == Decimal("0.00")  # el elemento existe con 0
    assert f.cargos is None  # el elemento no existe
    assert f.iva == Decimal("19000.00")
    assert f.otros_impuestos == Decimal("1600.00")
    assert f.anticipos is None
    assert f.retenciones == Decimal("5850.00")
    assert f.total == Decimal("140600.00")
    assert f.neto_a_pagar == Decimal("134750.00")
    assert len(f.lineas) == 2
    l1, l2 = f.lineas
    assert l1.descripcion == 'Taladro percutor 1/2"'
    assert l1.cantidad == Decimal("2")
    assert l1.valor_unitario == Decimal("50000")
    assert l1.valor_total == Decimal("100000.00")
    assert l1.tarifa_iva == Decimal("19")
    assert l1.iva == Decimal("19000.00")
    # Línea excluida: sin TaxTotal → tarifa e IVA nulos.
    assert l2.descripcion == "Servicio de instalación"
    assert l2.cantidad == Decimal("1")
    assert l2.valor_total == Decimal("20000.00")
    assert l2.tarifa_iva is None
    assert l2.iva is None
    # La factura sintética cuadra en todos los validadores de dominio.
    assert all(v.ok for v in validar_factura(f, HOY))


def test_invoice_xml_suelta() -> None:
    _check_invoice_fields(invoice_xml().encode("utf-8"))


def test_attached_document_con_cdata() -> None:
    _check_invoice_fields(attached_document(invoice_xml()).encode("utf-8"))


def test_zip_del_facturador() -> None:
    _check_invoice_fields(invoice_zip(attached_document(invoice_xml())))


def test_bom_y_espacios_iniciales() -> None:
    _check_invoice_fields(b"\xef\xbb\xbf\n  " + invoice_xml().encode("utf-8"))


@pytest.mark.parametrize(
    ("root", "kind"), [("CreditNote", "nota_credito"), ("DebitNote", "nota_debito")]
)
def test_notas_credito_y_debito(root: str, kind: str) -> None:
    ubl = parse_ubl(attached_document(invoice_xml(root, numero="NC-77")).encode("utf-8"))
    assert ubl.kind == kind
    assert ubl.factura.numero == "NC-77"
    assert ubl.factura.total == Decimal("140600.00")
    assert [line.cantidad for line in ubl.factura.lineas] == [Decimal("2"), Decimal("1")]


def test_dv_sin_scheme_id_es_null() -> None:
    ubl = parse_ubl(invoice_xml(dv_emisor=None).encode("utf-8"))
    assert ubl.factura.dv_emisor is None


def test_valor_invalido_se_anula_y_se_reporta() -> None:
    # NIT con letras: no pasa el esquema; el campo queda null y se informa como inválido.
    ubl = parse_ubl(invoice_xml(nit_adquirente="ABC123").encode("utf-8"))
    assert ubl.factura.nit_adquirente is None
    assert ubl.invalid == {"nit_adquirente": "ABC123"}
    assert ubl.factura.total == Decimal("140600.00")


def test_monto_con_mas_decimales_sin_perdida_se_normaliza() -> None:
    ubl = parse_ubl(invoice_xml(total="140600.000000").encode("utf-8"))
    assert ubl.factura.total == Decimal("140600.00")
    ubl = parse_ubl(invoice_xml(total="140600.004").encode("utf-8"))
    assert ubl.factura.total is None
    assert ubl.invalid == {"total": "140600.004"}


@pytest.mark.parametrize(
    "data",
    [
        b"<Invoice><no cierra>",
        b'<?xml version="1.0"?><Otra xmlns="urn:x"/>',
        attached_document("<ApplicationResponse/>").encode("utf-8"),
        b"PK\x03\x04 no es un zip",
    ],
)
def test_xml_no_reconocido(data: bytes) -> None:
    with pytest.raises(ExtractionError):
        parse_ubl(data)


def test_zip_sin_xml() -> None:
    with pytest.raises(ExtractionError, match="no contiene"):
        parse_ubl(invoice_zip(None))


def test_xxe_no_resuelve_entidades_externas() -> None:
    evil = b"""<?xml version="1.0"?>
<!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:ID>&x;</cbc:ID>
</Invoice>"""
    ubl = parse_ubl(evil)
    assert ubl.factura.numero is None or "root" not in ubl.factura.numero
