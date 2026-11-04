"""Texto de PDF con pypdfium2 (Apache-2.0/BSD-3; nada de PyMuPDF en `apps/`, ADR 0001 adenda).

La capa de texto se decide **página por página**: una página con menos de
`min_chars_per_page` caracteres visibles se trata como escaneada y va a OCR (hasta
`OcrLimits.max_pages` páginas con OCR; las demás se omiten y se informan).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import pypdfium2 as pdfium

from app.extraction.ocr import OcrEngine, OcrLimits, OcrUnavailableError, ocr_pdf_page
from app.extraction.types import ExtractionError


def visible_chars(text: str) -> int:
    return len("".join(text.split()))


@dataclass(frozen=True)
class PdfText:
    pages: list[str]

    def visible_chars(self) -> int:
        return sum(visible_chars(p) for p in self.pages)


@dataclass
class PdfRead:
    pages: list[str] = field(default_factory=list)
    ocr_pages: list[int] = field(default_factory=list)  # desde 1
    omitted: list[int] = field(default_factory=list)  # escaneadas sin OCR (límite o sin OCR)
    ocr_error: str | None = None  # por qué no hubo OCR, si faltó

    @property
    def used_ocr(self) -> bool:
        return bool(self.ocr_pages)


@contextmanager
def open_pdf(data: bytes) -> Iterator[Any]:
    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        raise ExtractionError(f"PDF ilegible o protegido con contraseña: {exc}") from exc
    try:
        yield pdf
    finally:
        pdf.close()


def _page_text(page: Any) -> str:
    textpage = page.get_textpage()
    try:
        return str(textpage.get_text_bounded()).replace("\r\n", "\n").strip()
    finally:
        textpage.close()


def extract_text(data: bytes) -> PdfText:
    """Solo la capa de texto, sin OCR."""
    pages: list[str] = []
    with open_pdf(data) as pdf:
        for i in range(len(pdf)):
            page = pdf[i]
            try:
                pages.append(_page_text(page))
            finally:
                page.close()
    return PdfText(pages)


def read_pdf(
    data: bytes,
    ocr_factory: Callable[[], OcrEngine],
    *,
    min_chars_per_page: int,
    limits: OcrLimits,
) -> PdfRead:
    """Texto de cada página; las páginas sin capa de texto pasan por OCR."""
    out = PdfRead()
    engine: OcrEngine | None = None
    with open_pdf(data) as pdf:
        for i in range(len(pdf)):
            page = pdf[i]
            try:
                text = _page_text(page)
                if visible_chars(text) >= min_chars_per_page:
                    out.pages.append(text)
                    continue
                if out.ocr_error is not None or len(out.ocr_pages) >= limits.max_pages:
                    out.omitted.append(i + 1)
                    out.pages.append(text)
                    continue
                if engine is None:
                    try:
                        engine = ocr_factory()
                    except OcrUnavailableError as exc:
                        out.ocr_error = str(exc)
                        out.omitted.append(i + 1)
                        out.pages.append(text)
                        continue
                out.pages.append(ocr_pdf_page(page, engine, limits))
                out.ocr_pages.append(i + 1)
            finally:
                page.close()
    return out
