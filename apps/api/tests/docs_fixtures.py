"""Documentos SINTÉTICOS generados en las pruebas (nada de data/ ni datos reales).

- Factura UBL 2.1, nota crédito/débito, AttachedDocument con la factura en CDATA y el ZIP.
- PDF con capa de texto (Helvetica, WinAnsi) y PDF "escaneado" sin texto.
- Imagen PNG.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import date

from PIL import Image, ImageDraw, ImageFont

from app.schemas.validators import calcular_dv

HOY = date(2026, 11, 4)

NIT_EMISOR = "900123456"
DV_EMISOR = calcular_dv(NIT_EMISOR)
NIT_ADQ = "800197268"
DV_ADQ = calcular_dv(NIT_ADQ)  # 4
CUFE = hashlib.sha384(b"factura-sintetica-1").hexdigest()

_NS = (
    'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
    'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" '
    'xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"'
)
_ROOT_NS = {
    "Invoice": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "CreditNote": "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2",
    "DebitNote": "urn:oasis:names:specification:ubl:schema:xsd:DebitNote-2",
}
_LINE = {
    "Invoice": ("InvoiceLine", "InvoicedQuantity", "LegalMonetaryTotal"),
    "CreditNote": ("CreditNoteLine", "CreditedQuantity", "LegalMonetaryTotal"),
    "DebitNote": ("DebitNoteLine", "DebitedQuantity", "RequestedMonetaryTotal"),
}


def _party(role: str, nit: str, dv: int | None, name: str) -> str:
    scheme = f' schemeID="{dv}"' if dv is not None else ""
    return f"""
  <cac:{role}>
    <cac:Party>
      <cac:PartyName><cbc:Name>{name}</cbc:Name></cac:PartyName>
      <cac:PartyTaxScheme>
        <cbc:RegistrationName>{name}</cbc:RegistrationName>
        <cbc:CompanyID schemeAgencyID="195" schemeName="31"{scheme}>{nit}</cbc:CompanyID>
        <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
      </cac:PartyTaxScheme>
    </cac:Party>
  </cac:{role}>"""


def _tax_total(amount: str, scheme: str, name: str, percent: str, base: str) -> str:
    return f"""
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="COP">{amount}</cbc:TaxAmount>
    <cac:TaxSubtotal>
      <cbc:TaxableAmount currencyID="COP">{base}</cbc:TaxableAmount>
      <cbc:TaxAmount currencyID="COP">{amount}</cbc:TaxAmount>
      <cac:TaxCategory>
        <cbc:Percent>{percent}</cbc:Percent>
        <cac:TaxScheme><cbc:ID>{scheme}</cbc:ID><cbc:Name>{name}</cbc:Name></cac:TaxScheme>
      </cac:TaxCategory>
    </cac:TaxSubtotal>
  </cac:TaxTotal>"""


def invoice_xml(
    root: str = "Invoice",
    *,
    numero: str = "SETP990000001",
    dv_emisor: int | None = DV_EMISOR,
    total: str = "140600.00",
    fecha: str = "2026-10-15",
    nit_adquirente: str = NIT_ADQ,
) -> str:
    """Factura sintética: 2 líneas (una gravada al 19 %, una excluida), INC y retenciones.

    subtotal 120000.00 + IVA 19000.00 + INC 1600.00 = total 140600.00;
    retenciones = ReteFuente 3000.00 + ReteIVA 2850.00 = 5850.00.
    """
    line_tag, qty_tag, totals_tag = _LINE[root]
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<{root} xmlns="{_ROOT_NS[root]}" {_NS}>
  <ext:UBLExtensions><ext:UBLExtension><ext:ExtensionContent/></ext:UBLExtension></ext:UBLExtensions>
  <cbc:UBLVersionID>UBL 2.1</cbc:UBLVersionID>
  <cbc:ID>{numero}</cbc:ID>
  <cbc:UUID schemeID="2" schemeName="CUFE-SHA384">{CUFE}</cbc:UUID>
  <cbc:IssueDate>{fecha}</cbc:IssueDate>
  <cbc:IssueTime>08:30:00-05:00</cbc:IssueTime>
  <cbc:DocumentCurrencyCode>COP</cbc:DocumentCurrencyCode>
  {_party("AccountingSupplierParty", NIT_EMISOR, dv_emisor, "FERRETERIA   EL TORNILLO S.A.S.")}
  {_party("AccountingCustomerParty", nit_adquirente, DV_ADQ, "COMERCIALIZADORA ÑANDÚ LTDA")}
  {_tax_total("19000.00", "01", "IVA", "19.00", "100000.00")}
  {_tax_total("1600.00", "04", "INC", "8.00", "20000.00")}
  <cac:WithholdingTaxTotal>
    <cbc:TaxAmount currencyID="COP">3000.00</cbc:TaxAmount>
  </cac:WithholdingTaxTotal>
  <cac:WithholdingTaxTotal>
    <cbc:TaxAmount currencyID="COP">2850.00</cbc:TaxAmount>
  </cac:WithholdingTaxTotal>
  <cac:{totals_tag}>
    <cbc:LineExtensionAmount currencyID="COP">120000.00</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="COP">100000.00</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="COP">140600.00</cbc:TaxInclusiveAmount>
    <cbc:AllowanceTotalAmount currencyID="COP">0.00</cbc:AllowanceTotalAmount>
    <cbc:PayableAmount currencyID="COP">{total}</cbc:PayableAmount>
  </cac:{totals_tag}>
  <cac:{line_tag}>
    <cbc:ID>1</cbc:ID>
    <cbc:{qty_tag} unitCode="EA">2.000000</cbc:{qty_tag}>
    <cbc:LineExtensionAmount currencyID="COP">100000.00</cbc:LineExtensionAmount>
    {_tax_total("19000.00", "01", "IVA", "19.00", "100000.00")}
    <cac:Item><cbc:Description>Taladro  percutor 1/2"</cbc:Description></cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="COP">50000.00</cbc:PriceAmount></cac:Price>
  </cac:{line_tag}>
  <cac:{line_tag}>
    <cbc:ID>2</cbc:ID>
    <cbc:{qty_tag} unitCode="EA">1</cbc:{qty_tag}>
    <cbc:LineExtensionAmount currencyID="COP">20000.00</cbc:LineExtensionAmount>
    <cac:Item><cbc:Description>Servicio de instalación</cbc:Description></cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="COP">20000.00</cbc:PriceAmount></cac:Price>
  </cac:{line_tag}>
</{root}>
"""


_APP_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?>
<ApplicationResponse xmlns="urn:oasis:names:specification:ubl:schema:xsd:ApplicationResponse-2">
  <cbc:ID
    xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">1</cbc:ID>
</ApplicationResponse>"""


def attached_document(inner: str) -> str:
    """AttachedDocument: factura en CDATA y respuesta DIAN en ParentDocumentLineReference."""
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<AttachedDocument xmlns="urn:oasis:names:specification:ubl:schema:xsd:AttachedDocument-2" {_NS}>
  <cbc:UBLVersionID>UBL 2.1</cbc:UBLVersionID>
  <cbc:ID>AD-0001</cbc:ID>
  <cac:ParentDocumentLineReference>
    <cbc:LineID>1</cbc:LineID>
    <cac:DocumentReference>
      <cbc:ID>SETP990000001</cbc:ID>
      <cac:Attachment>
        <cac:ExternalReference>
          <cbc:MimeCode>text/xml</cbc:MimeCode>
          <cbc:Description><![CDATA[{_APP_RESPONSE}]]></cbc:Description>
        </cac:ExternalReference>
      </cac:Attachment>
    </cac:DocumentReference>
  </cac:ParentDocumentLineReference>
  <cac:Attachment>
    <cac:ExternalReference>
      <cbc:MimeCode>text/xml</cbc:MimeCode>
      <cbc:EncodingCode>UTF-8</cbc:EncodingCode>
      <cbc:Description><![CDATA[{inner}]]></cbc:Description>
    </cac:ExternalReference>
  </cac:Attachment>
</AttachedDocument>
"""


def invoice_zip(xml: str | None = None, *, with_pdf: bool = True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if with_pdf:
            zf.writestr("fv09001234560002600000001.pdf", text_pdf(["Representación gráfica"]))
        if xml is not None:
            zf.writestr("ad09001234560002600000001.xml", xml.encode("utf-8"))
    return buf.getvalue()


# ------------------------------------------------------------------------------ PDF e imagen


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text_pdf(lines: list[str]) -> bytes:
    """PDF de una página con capa de texto real (Helvetica, WinAnsiEncoding)."""
    shows = " ".join(f"({_pdf_escape(line)}) '" for line in lines)
    content = f"BT /F1 11 Tf 14 TL 50 760 Td {shows} ET" if lines else ""
    return _pdf(content.encode("cp1252"))


def blank_pdf() -> bytes:
    """PDF sin capa de texto (como un escaneo: no hay nada que leer sin OCR)."""
    return _pdf(b"0.9 g 50 50 500 700 re f")


def _pdf(content: bytes) -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out = bytearray(b"%PDF-1.7\n")
    offsets = []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


def png_with_text(text: str = "CUENTA DE COBRO") -> bytes:
    img = Image.new("RGB", (1400, 220), "white")
    draw = ImageDraw.Draw(img)
    try:  # fuente del sistema con tildes y ñ; si no hay, la de Pillow
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont = ImageFont.truetype("arial.ttf", 56)
    except OSError:
        font = ImageFont.load_default(56)
    draw.text((40, 70), text, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def image_pdf(png: bytes) -> bytes:
    """PDF cuya página es solo una imagen (como un escaneo)."""
    buf = io.BytesIO()
    with Image.open(io.BytesIO(png)) as img:
        img.convert("RGB").save(buf, format="PDF", resolution=150)
    return buf.getvalue()


CUENTA_COBRO_LINES = [
    "CUENTA DE COBRO No. 015",
    "Medellín, 20 de octubre de 2026",
    "COMERCIALIZADORA ÑANDÚ LTDA NIT 800.197.268-4",
    "DEBE A:",
    "ANA MARÍA PÉREZ GÓMEZ C.C. 43.123.456",
    "La suma de UN MILLÓN QUINIENTOS MIL PESOS ($1.500.000)",
    "Por concepto de: asesoría contable del mes de octubre de 2026.",
    "Declaro que no soy responsable de IVA.",
]


def cuenta_cobro_json(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "tipo_documento": "cuenta_cobro",
        "numero": "015",
        "fecha": "2026-10-20",
        "ciudad": "Medellín",
        "nombre_cobrador": "ANA MARÍA PÉREZ GÓMEZ",
        "nit_cobrador": "43123456",
        "dv_cobrador": None,
        "nombre_pagador": "COMERCIALIZADORA ÑANDÚ LTDA",
        "nit_pagador": "800197268",
        "dv_pagador": 4,
        "concepto": "asesoría contable del mes de octubre de 2026.",
        "valor": "1500000.00",
        "declara_no_responsable_iva": True,
    }
    data.update(overrides)
    return data
