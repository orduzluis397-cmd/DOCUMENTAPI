"""Pruebas rápidas del anonimizador (solo regex; sin el modelo spaCy grande)."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest
from conftest import (
    Originales,
    attached_document_xml,
    factura_pdf,
    factura_xml,
    factura_zip,
)
from cryptography.fernet import Fernet
from lxml import etree

import anonymize as an

NIT_CON_DV = re.compile(r"(?<![\d.])((?:\d{1,3}(?:\.\d{3}){1,3}|\d{5,10}))\s?-\s?(\d)(?!\d)")


@pytest.fixture
def detector() -> an.Detector:
    return an.Detector(usar_ner=False)


def _sin_originales(texto: str, o: Originales, nombres: bool = True) -> None:
    excluidos = set() if nombres else {o.razon_social, o.nombre_adquirente}
    sensibles = [v for v in o.sensibles() if v not in excluidos]
    restantes = [v for v in sensibles if v.casefold() in texto.casefold()]
    assert restantes == []
    # Ni siquiera con los puntos quitados
    compacto = re.sub(r"[.\s]", "", texto)
    for numero in (o.nit_emisor, o.cc_adquirente, o.cc_corta, o.celular):
        assert numero not in compacto


def _dv_validos(texto: str) -> int:
    encontrados = NIT_CON_DV.findall(texto)
    for cuerpo, dv in encontrados:
        assert an.calcular_dv(cuerpo) == int(dv), f"DV inválido en {cuerpo}-{dv}"
    return len(encontrados)


# ---------------------------------------------------------------- DV


@pytest.mark.parametrize(
    ("nit", "dv"),
    [("800197268", 4), ("800.197.268", 4), ("900123456", 8), ("860034313", 7)],
)
def test_dv(nit: str, dv: int) -> None:
    assert an.calcular_dv(nit) == dv


def test_dv_rechaza_vacio() -> None:
    with pytest.raises(ValueError, match="NIT inválido"):
        an.calcular_dv("abc")


# ---------------------------------------------------------------- reconocedores


@pytest.mark.parametrize(
    ("texto", "entidad", "valor"),
    [
        ("NIT 900.123.456-8 emisor", an.NIT, "900.123.456-8"),
        ("nit: 900123456", an.NIT, "900123456"),
        # NIT de persona natural: cédula de longitud variable, con y sin DV
        ("NIT 1.020.304.050-1", an.NIT, "1.020.304.050-1"),
        ("NIT. 79123456", an.NIT, "79123456"),
        ("proveedor 79123456-1 Medellín", an.NIT, "79123456-1"),
        ("NIT No. 1234567", an.NIT, "1234567"),
        ("C.C. 52.345.678 de Bogotá", an.CEDULA, "52.345.678"),
        ("cédula de ciudadanía número 1020304050", an.CEDULA, "1020304050"),
        ("CC: 71654321", an.CEDULA, "71654321"),
        ("cel +57 310 555 1234.", an.CELULAR, "+57 310 555 1234"),
        ("whatsapp 3105551234", an.CELULAR, "3105551234"),
        ("tel (604) 444 5555", an.TELEFONO, "(604) 444 5555"),
        ("Cuenta de ahorros No. 123-456789-01", an.CUENTA, "123-456789-01"),
        ("correo: ana.p@empresa.com.co", an.CORREO, "ana.p@empresa.com.co"),
        ("vive en Cra. 45 No. 12-34 Apto 501", an.DIRECCION, "Cra. 45 No. 12-34 Apto 501"),
        ("Calle 10 # 43-21", an.DIRECCION, "Calle 10 # 43-21"),
        ("CUFE " + "ab12" * 24, an.CUFE, "ab12" * 24),
        ("CUFE: " + "a1b2c3" * 4, an.CUFE, "a1b2c3" * 4),  # tramo de un CUFE partido
    ],
)
def test_reconocedores(detector: an.Detector, texto: str, entidad: str, valor: str) -> None:
    hallazgos = detector.detectar(texto)
    assert (entidad, valor) in [(h.entidad, h.texto) for h in hallazgos]


@pytest.mark.parametrize(
    "texto",
    [
        "Subtotal 1.234.567 IVA 234.568",  # montos con puntos de miles
        "Fecha 2026-10-15",
        "Factura SETP990000001",
        "Total 119000.00",
    ],
)
def test_no_detecta_montos_ni_fechas(detector: an.Detector, texto: str) -> None:
    assert detector.detectar(texto) == []


# ---------------------------------------------------------------- reemplazos


def test_nit_falso_mismo_formato_y_dv_valido() -> None:
    rep = an.Reemplazador(semilla=7)
    for original in ("900.123.456-8", "1.020.304.050-1", "79123456-1", "52.345.678"):
        falso = rep.falso(an.NIT, original)
        assert falso != original
        assert re.sub(r"\d", "0", falso) == re.sub(r"\d", "0", original)  # mismo formato
        if "-" in original:
            cuerpo, dv = falso.rsplit("-", 1)
            assert an.calcular_dv(cuerpo) == int(dv)


def test_reemplazo_consistente_entre_formatos() -> None:
    rep = an.Reemplazador(semilla=1)
    con_formato = rep.falso(an.NIT, "900.123.456-8")
    sin_formato = rep.falso(an.NIT, "900123456")
    assert re.sub(r"\D", "", con_formato)[:9] == sin_formato
    # NIT de persona natural y su cédula comparten reemplazo
    assert re.sub(r"\D", "", rep.falso(an.CEDULA, "1.020.304.050")) == rep.falso(
        an.NIT, "1020304050"
    )
    # El falso no se vuelve a reemplazar
    assert rep.falso(an.NIT, sin_formato) == sin_formato


def test_celular_falso_mismo_formato() -> None:
    rep = an.Reemplazador(semilla=3)
    falso = rep.falso(an.CELULAR, "+57 310 555 1234")
    assert re.fullmatch(r"\+57 3\d{2} \d{3} \d{4}", falso)
    assert falso != "+57 310 555 1234"


# ---------------------------------------------------------------- XML


def test_xml_sin_originales_y_dv_valido(detector: an.Detector, originales: Originales) -> None:
    r = an.anonimizar_bytes(factura_xml().encode(), "xml", detector, an.Reemplazador(semilla=11))
    texto = r.datos.decode("utf-8")
    _sin_originales(texto, originales)
    raiz = etree.fromstring(r.datos)
    ids = raiz.findall(".//{*}CompanyID")
    assert len(ids) == 2
    for el in ids:
        assert el.text is not None
        assert el.get("schemeID") == str(an.calcular_dv(el.text))
    # Estructura y montos intactos
    assert raiz.findtext(".//{*}PayableAmount") == "119000.00"
    assert raiz.findtext(".//{*}IssueDate") == "2026-10-15"
    assert re.fullmatch(r"[0-9a-f]{96}", raiz.findtext(".//{*}UUID") or "")


def test_xml_consistente_dentro_del_documento(detector: an.Detector) -> None:
    r = an.anonimizar_bytes(factura_xml().encode(), "xml", detector, an.Reemplazador(semilla=5))
    raiz = etree.fromstring(r.datos)
    nombres = {el.text for el in raiz.iter("{*}RegistrationName", "{*}Name") if el.text}
    emisor = raiz.find(".//{*}AccountingSupplierParty//{*}PartyName/{*}Name")
    registro = raiz.find(".//{*}AccountingSupplierParty//{*}RegistrationName")
    assert emisor is not None
    assert registro is not None
    assert emisor.text == registro.text
    assert (emisor.text or "").endswith("S.A.S.")
    assert len(nombres) == 2


def test_attached_document_con_cdata(detector: an.Detector, originales: Originales) -> None:
    r = an.anonimizar_bytes(attached_document_xml().encode(), "xml", detector)
    texto = r.datos.decode("utf-8")
    _sin_originales(texto, originales)
    assert "<![CDATA[" in texto
    raiz = etree.fromstring(r.datos)
    interno = etree.fromstring((raiz.findtext(".//{*}Description") or "").encode())
    externo_nit = raiz.findtext(".//{*}SenderParty//{*}CompanyID")
    interno_nit = interno.findtext(".//{*}AccountingSupplierParty//{*}CompanyID")
    assert externo_nit == interno_nit  # el mismo NIT, el mismo falso


# ---------------------------------------------------------------- PDF


def test_pdf_sin_originales_incluida_capa_oculta(
    detector: an.Detector, originales: Originales
) -> None:
    entrada = factura_pdf()
    assert originales.cc_corta in an.texto_pdf(entrada)  # el fixture sí trae la capa oculta
    r = an.anonimizar_bytes(entrada, "pdf", detector, an.Reemplazador(semilla=2))
    texto = an.texto_pdf(r.datos)
    # Solo regex: la razón social con forma societaria sí se detecta; el nombre de persona en
    # texto libre de un PDF suelto requiere NER (prueba `modelo`) o el XML del mismo ZIP.
    assert originales.razon_social not in texto
    _sin_originales(texto, originales, nombres=False)
    assert "SETP990000001" in texto  # lo no sensible se conserva
    assert "Total 119000.00" in texto
    assert _dv_validos(texto) >= 2  # NIT falsos con DV válido sobre la página


def test_pdf_cifrado_falla(detector: an.Detector) -> None:
    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((40, 60), "NIT 900123456")
    datos = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="x", owner_pw="y")
    with pytest.raises(an.ErrorAnonimizacion, match="cifrado"):
        an.anonimizar_bytes(datos, "pdf", detector)


def test_verificacion_falla_cerrada() -> None:
    rep = an.Reemplazador()
    rep.falso(an.NIT, "900123456")
    with pytest.raises(an.ErrorAnonimizacion, match="quedan 1"):
        an._verificar("texto con 900.123.456 aún", rep, "PDF")


# ---------------------------------------------------------------- ZIP


def test_zip_xml_y_pdf_comparten_reemplazos(detector: an.Detector, originales: Originales) -> None:
    r = an.anonimizar_bytes(factura_zip(), "zip", detector, an.Reemplazador(semilla=9))
    with zipfile.ZipFile(io.BytesIO(r.datos)) as z:
        nombres = z.namelist()
        xml = z.read(next(n for n in nombres if n.endswith(".xml")))
        pdf = z.read(next(n for n in nombres if n.endswith(".pdf")))
    assert all(originales.nit_emisor not in n for n in nombres)
    texto_xml = xml.decode("utf-8")
    texto_pdf = an.texto_pdf(pdf)
    _sin_originales(texto_xml, originales)
    _sin_originales(texto_pdf, originales)
    nit_falso = etree.fromstring(xml).findtext(".//{*}SenderParty//{*}CompanyID") or ""
    assert nit_falso
    assert nit_falso in re.sub(r"\.", "", texto_pdf)
    nombre_falso = etree.fromstring(xml).findtext(".//{*}SenderParty//{*}RegistrationName") or ""
    assert nombre_falso in texto_pdf
    # El CUFE partido en dos líneas del PDF toma los tramos del CUFE falso del XML
    interno = etree.fromstring((etree.fromstring(xml).findtext(".//{*}Description") or "").encode())
    cufe_falso = interno.findtext(".//{*}UUID") or ""
    assert len(cufe_falso) == 96
    assert cufe_falso[:48] in texto_pdf
    assert cufe_falso[48:] in texto_pdf


# ---------------------------------------------------------------- tabla y CLI


def test_tabla_solo_bajo_data(tmp_path: Path) -> None:
    with pytest.raises(an.ErrorAnonimizacion, match="data/"):
        an.exigir_bajo_data(tmp_path / "fuera" / "t.mapping.enc")
    assert an.exigir_bajo_data(tmp_path / "data" / "t.mapping.enc")


def test_cli_escribe_salida_y_tabla_cifrada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    clave = Fernet.generate_key().decode()
    monkeypatch.setenv(an.ENV_CLAVE, clave)
    entrada = tmp_path / "data" / "raw" / "f.zip"
    entrada.parent.mkdir(parents=True)
    entrada.write_bytes(factura_zip())
    salida = tmp_path / "data" / "anonimizados" / "f.zip"
    assert an.main([str(entrada), str(salida), "--solo-regex", "--semilla", "4"]) == 0
    assert salida.exists()
    tabla = salida.with_name("f.zip.mapping.enc")
    crudo = tabla.read_bytes()
    assert b"900123456" not in crudo  # cifrada
    datos = an.leer_tabla(tabla, clave)
    originales = {p["original"] for p in datos["pares"]}
    assert "900123456" in originales
    salida_consola = capsys.readouterr()
    assert "900123456" not in salida_consola.out + salida_consola.err  # nunca se imprimen


def test_cli_sin_clave_falla(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(an.ENV_CLAVE, raising=False)
    entrada = tmp_path / "f.xml"
    entrada.write_text(factura_xml(), encoding="utf-8")
    salida = tmp_path / "data" / "f.xml"
    assert an.main([str(entrada), str(salida), "--solo-regex"]) == 1
    assert not salida.exists()


def test_cli_tabla_fuera_de_data_falla(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(an.ENV_CLAVE, Fernet.generate_key().decode())
    entrada = tmp_path / "f.xml"
    entrada.write_text(factura_xml(), encoding="utf-8")
    assert an.main([str(entrada), str(tmp_path / "f_anon.xml"), "--solo-regex"]) == 1
