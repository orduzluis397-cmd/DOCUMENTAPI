"""Fixtures sintéticos (nunca datos reales): XML UBL mínimo y PDF generados en el test."""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass

import pymupdf
import pytest

from anonymize import calcular_dv


@dataclass(frozen=True)
class Originales:
    nit_emisor: str = "900123456"
    razon_social: str = "FERRETERIA EL TORNILLO S.A.S."
    cc_adquirente: str = "1020304050"  # NIT de persona natural: cédula de 10 dígitos
    nombre_adquirente: str = "Laura Gomez Restrepo"
    cc_corta: str = "52345678"
    celular: str = "3105551234"
    celular_fmt: str = "+57 315 777 8899"
    fijo: str = "604 444 5555"
    correo: str = "laura.gomez@ferreteria-tornillo.co"
    direccion: str = "Calle 10 # 43-21"
    cuenta: str = "123-456789-01"
    cufe: str = hashlib.sha384(b"factura sintetica SETP990000001").hexdigest()

    @property
    def dv_emisor(self) -> int:
        return calcular_dv(self.nit_emisor)

    @property
    def nit_emisor_fmt(self) -> str:
        n = self.nit_emisor
        return f"{n[:3]}.{n[3:6]}.{n[6:]}-{self.dv_emisor}"

    @property
    def cc_adquirente_fmt(self) -> str:
        n = self.cc_adquirente
        return f"{n[0]}.{n[1:4]}.{n[4:7]}.{n[7:]}-{calcular_dv(n)}"

    def sensibles(self) -> list[str]:
        """Valores que no pueden quedar en ninguna salida."""
        return [
            self.nit_emisor,
            self.nit_emisor_fmt,
            self.razon_social,
            self.cc_adquirente,
            self.cc_adquirente_fmt,
            self.nombre_adquirente,
            self.cc_corta,
            "52.345.678",
            self.celular,
            self.celular_fmt,
            self.fijo,
            self.correo,
            self.direccion,
            self.cuenta,
            self.cufe,
            self.cufe[:48],  # el PDF lo parte en dos líneas
            self.cufe[48:],
        ]


ORIG = Originales()

NS = (
    'xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" '
    'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
    'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
    'xmlns:ds="http://www.w3.org/2000/09/xmldsig#"'
)


def factura_xml(o: Originales = ORIG) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice {NS}>
  <ds:Signature><ds:SignatureValue>QUJDREVGR0g=</ds:SignatureValue>
    <ds:KeyInfo><ds:X509Data>
      <ds:X509Certificate>TUlJQ2VydGlmaWNhZG9GYWxzbw==</ds:X509Certificate>
      <ds:X509SubjectName>CN={o.razon_social},serialNumber={o.nit_emisor}</ds:X509SubjectName>
    </ds:X509Data></ds:KeyInfo></ds:Signature>
  <cbc:ID>SETP990000001</cbc:ID>
  <cbc:UUID schemeName="CUFE-SHA384">{o.cufe}</cbc:UUID>
  <cbc:IssueDate>2026-10-15</cbc:IssueDate>
  <cbc:Note>Pagar a la cuenta de ahorros No. {o.cuenta}. Contacto cel {o.celular}.</cbc:Note>
  <cac:AccountingSupplierParty><cac:Party>
    <cac:PartyName><cbc:Name>{o.razon_social}</cbc:Name></cac:PartyName>
    <cac:PhysicalLocation><cac:Address><cbc:CityName>Medellín</cbc:CityName>
      <cac:AddressLine><cbc:Line>{o.direccion}</cbc:Line></cac:AddressLine>
    </cac:Address></cac:PhysicalLocation>
    <cac:PartyTaxScheme>
      <cbc:RegistrationName>{o.razon_social}</cbc:RegistrationName>
      <cbc:CompanyID schemeAgencyID="195" schemeID="{o.dv_emisor}"
        schemeName="31">{o.nit_emisor}</cbc:CompanyID>
    </cac:PartyTaxScheme>
    <cac:Contact><cbc:Telephone>{o.fijo}</cbc:Telephone>
      <cbc:ElectronicMail>{o.correo}</cbc:ElectronicMail></cac:Contact>
  </cac:Party></cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty><cac:Party>
    <cac:PartyTaxScheme>
      <cbc:RegistrationName>{o.nombre_adquirente}</cbc:RegistrationName>
      <cbc:CompanyID schemeAgencyID="195" schemeID="{calcular_dv(o.cc_adquirente)}"
        schemeName="31">{o.cc_adquirente}</cbc:CompanyID>
    </cac:PartyTaxScheme>
  </cac:Party></cac:AccountingCustomerParty>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="COP">100000.00</cbc:LineExtensionAmount>
    <cbc:PayableAmount currencyID="COP">119000.00</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
</Invoice>
"""


def attached_document_xml(o: Originales = ORIG) -> str:
    """AttachedDocument con la factura embebida en CDATA, como la envía la DIAN."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<AttachedDocument xmlns="urn:oasis:names:specification:ubl:schema:xsd:AttachedDocument-2"
  xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cac:SenderParty><cac:PartyTaxScheme>
    <cbc:RegistrationName>{o.razon_social}</cbc:RegistrationName>
    <cbc:CompanyID schemeID="{o.dv_emisor}" schemeName="31">{o.nit_emisor}</cbc:CompanyID>
  </cac:PartyTaxScheme></cac:SenderParty>
  <cac:Attachment><cac:ExternalReference>
    <cbc:Description><![CDATA[{factura_xml(o).strip()}]]></cbc:Description>
  </cac:ExternalReference></cac:Attachment>
</AttachedDocument>
"""


def factura_pdf(o: Originales = ORIG) -> bytes:
    """Representación gráfica sintética con texto visible, capa oculta (OCR) y metadatos."""
    doc = pymupdf.open()
    pagina = doc.new_page()
    lineas = [
        o.razon_social,
        f"NIT: {o.nit_emisor_fmt}",
        f"Dirección: {o.direccion} - Medellín",
        f"Tel: {o.fijo}  Cel: {o.celular_fmt}",
        f"Correo: {o.correo}",
        "FACTURA ELECTRÓNICA DE VENTA SETP990000001",
        f"Cliente: {o.nombre_adquirente}  NIT {o.cc_adquirente_fmt}",
        f"Autorizado: C.C. 52.345.678  cuenta de ahorros No. {o.cuenta}",
        f"CUFE: {o.cufe[:48]}",
        f"{o.cufe[48:]}",
        "Subtotal 100000.00  IVA 19000.00  Total 119000.00",
    ]
    y = 60.0
    for linea in lineas:
        pagina.insert_text((40, y), linea, fontsize=9)
        y += 16
    # Capa de texto oculta (render_mode=3), como la de un OCR.
    pagina.insert_text((40, 400), f"cedula {o.cc_corta} cel {o.celular}", fontsize=9, render_mode=3)
    pagina.insert_text((40, 420), f"{o.correo} {o.nit_emisor}", fontsize=9, render_mode=3)
    doc.set_metadata({"author": o.nombre_adquirente, "title": f"Factura {o.razon_social}"})
    datos: bytes = doc.tobytes()
    doc.close()
    return datos


def factura_zip(o: Originales = ORIG) -> bytes:
    buffer = io.BytesIO()
    nombre = f"ad0{o.nit_emisor}0002600000001"
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr(f"{nombre}.pdf", factura_pdf(o))
        z.writestr(f"{nombre}.xml", attached_document_xml(o))
    return buffer.getvalue()


@pytest.fixture
def originales() -> Originales:
    return ORIG
