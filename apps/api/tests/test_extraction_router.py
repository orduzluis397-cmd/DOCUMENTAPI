"""Enrutamiento por tipo de archivo (sin BD ni red): XML/ZIP → parser; PDF → texto u OCR por
página; imagen → OCR. Las rutas con LLM se cortan con un LLM "no configurado" para ver la ruta."""

from __future__ import annotations

import pytest
from PIL import Image

from app.config import Settings
from app.extraction.ocr import (
    MAX_IMAGE_PIXELS,
    OcrEngine,
    OcrLimits,
    OcrUnavailableError,
    TesseractOcr,
    fit_pixels,
    ocr_image,
    render_scale,
    tesseract_path,
)
from app.extraction.pdf_text import extract_text, read_pdf, visible_chars
from app.extraction.router import RouterConfig, extract_document
from app.extraction.types import ExtractionOutcome
from app.llm.base import LLMNotConfiguredError
from app.observability.llm_calls import TrackedLLM
from tests.docs_fixtures import (
    CUENTA_COBRO_LINES,
    HOY,
    attached_document,
    blank_pdf,
    image_pdf,
    invoice_xml,
    invoice_zip,
    mixed_pdf,
    multi_frame_tiff,
    png_with_text,
    text_pdf,
)
from tests.fakes import fake_ocr_factory

CONFIG = RouterConfig(model_extraction="modelo-falso", max_retries=1)


def _no_llm() -> TrackedLLM:
    raise LLMNotConfiguredError("prueba: sin LLM")


def _no_ocr() -> OcrEngine:
    raise OcrUnavailableError("OCR no disponible: Tesseract no está instalado (prueba)")


def _route(data: bytes, ocr: object = _no_ocr, config: RouterConfig = CONFIG) -> ExtractionOutcome:
    return extract_document(
        data,
        config=config,
        llm_factory=_no_llm,
        ocr_factory=ocr,  # type: ignore[arg-type]
        trace_id="t-1",
        hoy=HOY,
    )


def test_pdf_text_layer_detected() -> None:
    pdf = extract_text(text_pdf(CUENTA_COBRO_LINES))
    assert "CUENTA DE COBRO No. 015" in pdf.pages[0]
    assert "Medellín" in pdf.pages[0]
    assert visible_chars(pdf.pages[0]) >= 25
    assert extract_text(blank_pdf()).visible_chars() == 0


@pytest.mark.parametrize(
    "data",
    [
        invoice_xml().encode("utf-8"),
        attached_document(invoice_xml()).encode("utf-8"),
        invoice_zip(attached_document(invoice_xml())),
    ],
    ids=["xml", "attached", "zip"],
)
def test_xml_routes_to_parser_without_llm(data: bytes) -> None:
    def boom() -> TrackedLLM:
        raise AssertionError("la ruta XML no debe construir el LLM")

    out = extract_document(
        data, config=CONFIG, llm_factory=boom, ocr_factory=_no_ocr, trace_id="t", hoy=HOY
    )
    assert out.method == "xml_parser"
    assert out.status == "extracted", out.error
    assert out.doc_type == "factura"
    assert out.model is None
    values = {f.name: f.value for f in out.fields}
    assert values["total"] == "140600.00"
    assert values["lineas[1].descripcion"] == "Servicio de instalación"
    assert not out.doubtful_fields


def test_xml_with_invalid_dv_is_doubtful() -> None:
    out = _route(invoice_xml(dv_emisor=0).encode("utf-8"))
    assert out.status == "needs_review"
    assert set(out.doubtful_fields) == {"nit_emisor", "dv_emisor"}
    assert "dv_emisor" in (out.error or "")


def test_xml_total_mismatch_marks_amounts() -> None:
    out = _route(invoice_xml(total="150000.00").encode("utf-8"))
    assert out.status == "needs_review"
    assert {"subtotal", "iva", "total"} <= set(out.doubtful_fields)
    assert not any(f.startswith("lineas") for f in out.doubtful_fields)


def test_credit_note_needs_review() -> None:
    out = _route(attached_document(invoice_xml("CreditNote")).encode("utf-8"))
    assert out.method == "xml_parser"
    assert out.doc_type == "nota_credito"
    assert out.status == "needs_review"
    assert "Nota crédito" in (out.error or "")


def test_broken_xml_fails() -> None:
    out = _route(b"<?xml version='1.0'?><Invoice>")
    assert out.status == "failed"
    assert out.method == "xml_parser"


def test_text_pdf_routes_to_pdf_text_then_llm() -> None:
    out = _route(text_pdf(CUENTA_COBRO_LINES))
    assert out.method == "pdf_text"
    assert out.status == "failed"
    assert "LLM no configurado" in (out.error or "")
    assert out.raw_output["paginas"] == 1


def test_scanned_pdf_routes_to_ocr() -> None:
    ocr = fake_ocr_factory("texto leído por OCR")
    out = _route(blank_pdf(), ocr)
    assert out.method == "ocr"
    assert ocr().calls == 1
    assert "LLM no configurado" in (out.error or "")


def test_pdf_layer_is_decided_page_by_page() -> None:
    # Páginas 1 y 3 con texto; la 2 escaneada: solo la 2 va a OCR.
    ocr = fake_ocr_factory("PÁGINA ESCANEADA LEÍDA POR OCR")
    data = mixed_pdf([CUENTA_COBRO_LINES, None, CUENTA_COBRO_LINES])
    read = read_pdf(data, ocr, min_chars_per_page=25, limits=OcrLimits())
    assert read.ocr_pages == [2]
    assert read.omitted == []
    assert ocr().calls == 1
    assert "CUENTA DE COBRO" in read.pages[0]
    assert read.pages[1] == "PÁGINA ESCANEADA LEÍDA POR OCR"
    out = _route(data, ocr)
    assert out.method == "ocr"
    assert out.raw_output["paginas_ocr"] == [2]


def test_pages_over_ocr_limit_are_reported_and_need_review() -> None:
    ocr = fake_ocr_factory("texto OCR")
    config = RouterConfig(model_extraction="modelo-falso", ocr_max_pages=2)
    out = _route(mixed_pdf([None, None, None, CUENTA_COBRO_LINES]), ocr, config)
    assert ocr().calls == 2
    assert out.raw_output["paginas_omitidas"] == [3]
    assert "Páginas sin leer" in (out.error or "")


def test_pages_omitted_force_needs_review_even_if_extracted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.extraction import router

    def fake_from_text(*_args: object, **_kw: object) -> ExtractionOutcome:
        return ExtractionOutcome(status="extracted", method="ocr")

    monkeypatch.setattr(router, "_from_text", fake_from_text)
    config = RouterConfig(model_extraction="modelo-falso", ocr_max_pages=1)
    out = _route(mixed_pdf([None, None]), fake_ocr_factory("x"), config)
    assert out.status == "needs_review"
    assert out.raw_output["paginas_omitidas"] == [2]


def test_mixed_pdf_without_ocr_keeps_text_pages() -> None:
    out = _route(mixed_pdf([CUENTA_COBRO_LINES, None]))
    assert out.method == "pdf_text"
    assert out.raw_output["paginas_omitidas"] == [2]
    assert "OCR no disponible" in out.raw_output["ocr_no_disponible"]


def test_image_routes_to_ocr() -> None:
    ocr = fake_ocr_factory("CUENTA DE COBRO")
    out = _route(png_with_text(), ocr)
    assert out.method == "ocr"
    assert ocr().calls == 1


def test_tiff_frames_respect_page_limit() -> None:
    ocr = fake_ocr_factory("cuadro")
    result = ocr_image(multi_frame_tiff(4), ocr(), OcrLimits(max_pages=2))
    assert len(result.pages) == 2
    assert result.omitted == [3, 4]
    assert ocr().calls == 2


def test_pixel_caps() -> None:
    assert Image.MAX_IMAGE_PIXELS == MAX_IMAGE_PIXELS
    big = Image.new("RGB", (4000, 4000))
    small = fit_pixels(big, 4_000_000)
    assert small.size[0] * small.size[1] <= 4_000_000
    # Página carta a 300 dpi ≈ 8.4 MP; con tope de 2 MP la escala baja.
    scale = render_scale(612, 792, 300, 2_000_000)
    assert 612 * scale * 792 * scale <= 2_000_000 * 1.0001
    assert render_scale(612, 792, 300, 25_000_000) == pytest.approx(300 / 72)


def test_ocr_unavailable_is_clear_failure() -> None:
    out = _route(png_with_text())
    assert out.status == "failed"
    assert out.method == "ocr"
    assert "OCR no disponible" in (out.error or "")


def test_ocr_empty_text_needs_review() -> None:
    out = _route(png_with_text(), fake_ocr_factory("   "))
    assert out.status == "needs_review"
    assert "texto legible" in (out.error or "")


def test_unknown_file_fails() -> None:
    out = _route(b"MZ\x90\x00 ejecutable")
    assert out.status == "failed"


def test_tesseract_missing_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.extraction.ocr.shutil.which", lambda _cmd: None)
    with pytest.raises(OcrUnavailableError, match="TESSERACT_CMD"):
        TesseractOcr("C:/no/existe/tesseract.exe")


# ------------------------------------------------------------------------------ OCR real


def _real_ocr() -> TesseractOcr:
    s = Settings()
    return TesseractOcr(s.tesseract_cmd, s.ocr_lang, s.tessdata_prefix, s.ocr_timeout_s)


def _ocr_unavailable_reason() -> str | None:
    if tesseract_path(Settings().tesseract_cmd) is None:
        return "Tesseract no está instalado (ruta OCR no disponible)"
    try:
        _real_ocr()
    except OcrUnavailableError as exc:
        return str(exc)
    return None


_OCR_SKIP = _ocr_unavailable_reason()
# Pruebas de OCR real: se SALTAN sin Tesseract + idioma spa (p. ej. en CI).
requires_tesseract = pytest.mark.skipif(_OCR_SKIP is not None, reason=_OCR_SKIP or "")


@requires_tesseract
def test_real_tesseract_reads_image() -> None:
    engine = _real_ocr()
    out = _route(png_with_text("CUENTA DE COBRO"), lambda: engine)
    assert out.method == "ocr"
    assert "LLM no configurado" in (out.error or "")


@requires_tesseract
def test_real_tesseract_spanish_text() -> None:
    result = ocr_image(png_with_text("CUENTA DE COBRO 15 MEDELLÍN"), _real_ocr())
    text = result.pages[0].upper()
    assert "CUENTA DE COBRO" in text
    assert "MEDELLÍN" in text


@requires_tesseract
def test_real_tesseract_scanned_pdf() -> None:
    # PDF "escaneado": la página es una imagen sin capa de texto → render con pypdfium2 + OCR.
    engine = _real_ocr()
    read = read_pdf(
        image_pdf(png_with_text("EXTRACTO BANCARIO")),
        lambda: engine,
        min_chars_per_page=25,
        limits=OcrLimits(dpi=150),
    )
    assert read.ocr_pages == [1]
    assert "EXTRACTO" in read.pages[0].upper()
