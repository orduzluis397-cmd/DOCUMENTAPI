"""Parser determinista UBL 2.1 (sin LLM), campo por campo, con fixtures sintéticos."""

import io
import time
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from lxml import etree

from app.extraction import xml_ubl
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
    # Sin ceros de relleno (UBL trae "19.00" y "2.000000"): igual que GUIA.md y la ruta LLM.
    assert (str(l1.tarifa_iva), str(l1.cantidad), str(l1.valor_unitario)) == ("19", "2", "50000")
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


_INVOICE_OPEN = (
    b'<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" '
    b'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">'
)


def test_xxe_no_resuelve_entidades_externas(tmp_path: Path) -> None:
    # Archivo local con un token conocido: si el parser resolviera la entidad, aparecería.
    secret = tmp_path / "secreto.txt"
    marker = "MARCA-XXE-1234"
    secret.write_text(marker, encoding="utf-8")
    evil = (
        b'<?xml version="1.0"?>\n<!DOCTYPE r [<!ENTITY x SYSTEM "'
        + secret.as_uri().encode()
        + b'">]>\n'
        + _INVOICE_OPEN
        + b"<cbc:ID>&x;</cbc:ID></Invoice>"
    )
    # 1) El parser de bajo nivel no resuelve la entidad: el número queda vacío.
    root = etree.fromstring(evil, parser=xml_ubl._parser())
    numero = root.find("cbc:ID", xml_ubl.NS)
    assert numero is not None
    assert numero.text is None
    assert marker not in etree.tostring(root).decode()
    # 2) Y el documento se rechaza por traer DOCTYPE.
    with pytest.raises(ExtractionError, match="DOCTYPE") as exc:
        parse_ubl(evil)
    assert marker not in str(exc.value)


def test_billion_laughs_se_rechaza_rapido() -> None:
    entities = b'<!ENTITY a0 "jajaja">' + b"".join(
        b'<!ENTITY a%d "&a%d;&a%d;&a%d;&a%d;&a%d;&a%d;&a%d;&a%d;&a%d;&a%d;">' % (i, *([i - 1] * 10))
        for i in range(1, 10)
    )
    evil = b"<?xml version='1.0'?><!DOCTYPE r [" + entities + b"]>" + _INVOICE_OPEN
    evil += b"<cbc:ID>&a9;</cbc:ID></Invoice>"
    start = time.perf_counter()
    with pytest.raises(ExtractionError):
        parse_ubl(evil)
    assert time.perf_counter() - start < 2


def test_doctype_simple_se_rechaza() -> None:
    xml = invoice_xml().replace(
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
        '<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE Invoice>',
    )
    with pytest.raises(ExtractionError, match="DOCTYPE"):
        parse_ubl(xml.encode("utf-8"))
    # También dentro del CDATA del AttachedDocument.
    with pytest.raises(ExtractionError):
        parse_ubl(attached_document(xml).encode("utf-8"))


@pytest.mark.parametrize("total", ["1.4060E+5", "1e400", "9" * 40 + ".00", "NaN", "Infinity"])
def test_montos_extremos_o_cientificos_quedan_invalidos(total: str) -> None:
    ubl = parse_ubl(invoice_xml(total=total).encode("utf-8"))
    assert ubl.factura.total is None
    assert ubl.invalid == {"total": total}


def test_zip_cifrado_o_con_compresion_no_soportada() -> None:
    original = invoice_zip(attached_document(invoice_xml()), with_pdf=False)
    central = original.find(b"PK\x01\x02")
    # Bit 0 de los flags (cabecera local: offset 6; central: offset 8) = cifrado.
    data = bytearray(original)
    data[6] |= 0x1
    data[central + 8] |= 0x1
    with pytest.raises(ExtractionError, match="cifrado"):
        parse_ubl(bytes(data))
    # Método de compresión 99 (local: offset 8; central: offset 10) = no soportado.
    data = bytearray(original)
    data[8:10] = (99).to_bytes(2, "little")
    data[central + 10 : central + 12] = (99).to_bytes(2, "little")
    with pytest.raises(ExtractionError, match="no se puede leer"):
        parse_ubl(bytes(data))
    assert zipfile.is_zipfile(io.BytesIO(bytes(data)))


def test_zip_tope_total_descomprimido(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(xml_ubl, "_ZIP_MAX_TOTAL_BYTES", 100)
    with pytest.raises(ExtractionError, match="descomprimidos"):
        parse_ubl(invoice_zip(attached_document(invoice_xml())))
