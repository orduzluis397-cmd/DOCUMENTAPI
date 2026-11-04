"""Parser determinista de factura electrónica DIAN (UBL 2.1), sin LLM (regla dura 7).

Acepta:

- El ZIP que entrega el facturador (contiene el `AttachedDocument` y la representación gráfica).
- El `AttachedDocument` suelto: la factura va en CDATA en
  `cac:Attachment/cac:ExternalReference/cbc:Description`.
- La `Invoice`, `CreditNote` o `DebitNote` UBL 2.1 suelta.

El mapeo de campos sigue `evals/datasets/GUIA.md` §4. Las notas crédito/débito se leen con el
mismo esquema `Factura` (mismos componentes UBL) mientras `datos-corpus` define su esquema propio.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from lxml import etree

from app.extraction.fields import salvage
from app.extraction.types import ExtractionError
from app.schemas import Factura

UblKind = Literal["factura", "nota_credito", "nota_debito"]

NS = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}
_ROOTS: dict[str, tuple[UblKind, str, str, str]] = {
    # raíz: (tipo, elemento de línea, cantidad de la línea, totales monetarios)
    "Invoice": ("factura", "InvoiceLine", "InvoicedQuantity", "LegalMonetaryTotal"),
    "CreditNote": ("nota_credito", "CreditNoteLine", "CreditedQuantity", "LegalMonetaryTotal"),
    "DebitNote": ("nota_debito", "DebitNoteLine", "DebitedQuantity", "RequestedMonetaryTotal"),
}
_IVA = "01"
_ZIP_MAX_ENTRIES = 50
_ZIP_MAX_XML_BYTES = 20 * 1024 * 1024
_CENT = Decimal("0.01")
_MICRO = Decimal("0.000001")


def _parser() -> etree.XMLParser:
    # Sin DTD, sin entidades externas ni red (XXE / billion laughs).
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
    )


@dataclass(frozen=True)
class UblDocument:
    kind: UblKind
    factura: Factura
    # Campos que el XML trae pero no pasan el esquema (se anulan y se marcan dudosos).
    invalid: dict[str, Any]


def is_zip(data: bytes) -> bool:
    return data.startswith(b"PK\x03\x04")


def parse_ubl(data: bytes) -> UblDocument:
    """ZIP, `AttachedDocument` o documento UBL → `Factura`. Lanza `ExtractionError`."""
    xml = _xml_from_zip(data) if is_zip(data) else data
    root = _parse(xml)
    root = _unwrap(root)
    local = etree.QName(root).localname
    if local not in _ROOTS:
        raise ExtractionError(f"XML no reconocido como factura electrónica UBL 2.1 ({local})")
    kind, line_tag, qty_tag, totals_tag = _ROOTS[local]
    raw = _read_document(root, line_tag, qty_tag, totals_tag)
    factura, invalid = salvage(Factura, raw, "factura")
    if factura is None:  # pragma: no cover - salvage siempre puede anular hasta validar
        raise ExtractionError("El XML no se pudo convertir al esquema Factura")
    return UblDocument(kind=kind, factura=factura, invalid=invalid)


# ------------------------------------------------------------------------------ contenedores


def _parse(xml: bytes | str) -> etree._Element:
    if isinstance(xml, str):
        xml = xml.encode("utf-8")
    try:
        return etree.fromstring(xml.removeprefix(b"\xef\xbb\xbf").lstrip(), parser=_parser())
    except etree.XMLSyntaxError as exc:
        raise ExtractionError(f"XML mal formado: {exc}") from exc


def _xml_from_zip(data: bytes) -> bytes:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ExtractionError("ZIP dañado") from exc
    with zf:
        entries = [i for i in zf.infolist() if not i.is_dir()]
        if len(entries) > _ZIP_MAX_ENTRIES:
            raise ExtractionError(f"ZIP con demasiados archivos ({len(entries)})")
        for info in entries:
            if not info.filename.lower().endswith(".xml"):
                continue
            with zf.open(info) as fh:
                # Lectura acotada: no se confía en el tamaño declarado (zip bomb).
                content = fh.read(_ZIP_MAX_XML_BYTES + 1)
            if len(content) > _ZIP_MAX_XML_BYTES:
                raise ExtractionError(f"{info.filename}: XML demasiado grande dentro del ZIP")
            try:
                root = _unwrap(_parse(content))
            except ExtractionError:
                continue
            if etree.QName(root).localname in _ROOTS:
                return content
    raise ExtractionError("El ZIP no contiene una factura electrónica XML")


def _unwrap(root: etree._Element) -> etree._Element:
    """Si es un `AttachedDocument`, devuelve la factura/nota embebida en CDATA."""
    if etree.QName(root).localname != "AttachedDocument":
        return root
    # Primero el adjunto directo del AttachedDocument; luego cualquiera (la respuesta de la DIAN
    # en ParentDocumentLineReference es un ApplicationResponse y se descarta).
    candidates = root.findall("cac:Attachment/cac:ExternalReference/cbc:Description", NS)
    candidates += root.findall(".//cac:Attachment/cac:ExternalReference/cbc:Description", NS)
    for desc in candidates:
        text = (desc.text or "").strip()
        if not text.startswith("<"):
            continue
        try:
            inner = _parse(text)
        except ExtractionError:
            continue
        if etree.QName(inner).localname in _ROOTS:
            return inner
    raise ExtractionError("AttachedDocument sin factura o nota embebida")


# ------------------------------------------------------------------------------ campos


def _text(el: etree._Element | None, path: str) -> str | None:
    if el is None:
        return None
    found = el.find(path, NS)
    if found is None or found.text is None:
        return None
    collapsed = " ".join(found.text.split())
    return collapsed or None


def _amount(text: str | None, quantum: Decimal = _CENT) -> Decimal | str | None:
    """Decimal normalizado a `quantum` si no pierde precisión; si no, el texto (lo marca el
    esquema)."""
    if text is None:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return text
    if not value.is_finite():
        return text
    rounded = value.quantize(quantum)
    return rounded if rounded == value else text


def _sum(values: list[Decimal | str | None]) -> Decimal | str | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    bad = [v for v in present if not isinstance(v, Decimal)]
    if bad:
        return bad[0]
    return sum((v for v in present if isinstance(v, Decimal)), Decimal("0.00"))


def _party(root: etree._Element, role: str) -> tuple[str | None, Any, str | None]:
    party = root.find(f"cac:{role}/cac:Party", NS)
    if party is None:
        return None, None, None
    company = party.find("cac:PartyTaxScheme/cbc:CompanyID", NS)
    if company is None:
        company = party.find("cac:PartyLegalEntity/cbc:CompanyID", NS)
    nit: str | None = None
    dv: Any = None
    if company is not None:
        nit = " ".join((company.text or "").split()) or None
        scheme = (company.get("schemeID") or "").strip()
        dv = int(scheme) if scheme.isdigit() and len(scheme) == 1 else (scheme or None)
    name = (
        _text(party, "cac:PartyTaxScheme/cbc:RegistrationName")
        or _text(party, "cac:PartyLegalEntity/cbc:RegistrationName")
        or _text(party, "cac:PartyName/cbc:Name")
    )
    return nit, dv, name


def _taxes(el: etree._Element) -> tuple[Decimal | str | None, Decimal | str | None]:
    """(IVA, otros impuestos) sumando los `TaxSubtotal` de los `TaxTotal` hijos directos."""
    iva: list[Decimal | str | None] = []
    otros: list[Decimal | str | None] = []
    for total in el.findall("cac:TaxTotal", NS):
        subtotals = total.findall("cac:TaxSubtotal", NS)
        if not subtotals:
            otros.append(_amount(_text(total, "cbc:TaxAmount")))
            continue
        for sub in subtotals:
            scheme = _text(sub, "cac:TaxCategory/cac:TaxScheme/cbc:ID")
            (iva if scheme == _IVA else otros).append(_amount(_text(sub, "cbc:TaxAmount")))
    return _sum(iva), _sum(otros)


def _line(line: etree._Element, qty_tag: str) -> dict[str, Any]:
    tarifa: Decimal | str | None = None
    for sub in line.findall("cac:TaxTotal/cac:TaxSubtotal", NS):
        if _text(sub, "cac:TaxCategory/cac:TaxScheme/cbc:ID") == _IVA:
            tarifa = _amount(_text(sub, "cac:TaxCategory/cbc:Percent"), _MICRO)
            break
    iva, _ = _taxes(line)
    return {
        "descripcion": _text(line, "cac:Item/cbc:Description"),
        "cantidad": _amount(_text(line, f"cbc:{qty_tag}"), _MICRO),
        "valor_unitario": _amount(_text(line, "cac:Price/cbc:PriceAmount"), _MICRO),
        "valor_total": _amount(_text(line, "cbc:LineExtensionAmount")),
        "tarifa_iva": tarifa,
        "iva": iva,
    }


def _read_document(
    root: etree._Element, line_tag: str, qty_tag: str, totals_tag: str
) -> dict[str, Any]:
    nit_e, dv_e, name_e = _party(root, "AccountingSupplierParty")
    nit_a, dv_a, name_a = _party(root, "AccountingCustomerParty")
    totals = root.find(f"cac:{totals_tag}", NS)
    iva, otros = _taxes(root)
    retenciones = _sum(
        [_amount(_text(w, "cbc:TaxAmount")) for w in root.findall("cac:WithholdingTaxTotal", NS)]
    )
    return {
        "numero": _text(root, "cbc:ID"),
        "cufe": _text(root, "cbc:UUID"),
        "fecha_emision": _text(root, "cbc:IssueDate"),
        "nit_emisor": nit_e,
        "dv_emisor": dv_e,
        "razon_social_emisor": name_e,
        "nit_adquirente": nit_a,
        "dv_adquirente": dv_a,
        "razon_social_adquirente": name_a,
        "subtotal": _amount(_text(totals, "cbc:LineExtensionAmount")),
        "descuentos": _amount(_text(totals, "cbc:AllowanceTotalAmount")),
        "cargos": _amount(_text(totals, "cbc:ChargeTotalAmount")),
        "iva": iva,
        "otros_impuestos": otros,
        "anticipos": _amount(_text(totals, "cbc:PrepaidAmount")),
        "retenciones": retenciones,
        "total": _amount(_text(totals, "cbc:PayableAmount")),
        "lineas": [_line(line, qty_tag) for line in root.findall(f"cac:{line_tag}", NS)],
    }
