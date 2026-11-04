"""Texto de PDF con pypdfium2 (Apache-2.0/BSD-3; nada de PyMuPDF en `apps/`, ADR 0001 adenda)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import pypdfium2 as pdfium

from app.extraction.types import ExtractionError


@dataclass(frozen=True)
class PdfText:
    pages: list[str]

    @property
    def text(self) -> str:
        return "\n\n".join(f"--- página {i} ---\n{t}" for i, t in enumerate(self.pages, 1))

    def visible_chars(self) -> int:
        return sum(len("".join(p.split())) for p in self.pages)

    def has_text_layer(self, min_chars_per_page: int) -> bool:
        """Capa de texto útil: en promedio al menos `min_chars_per_page` caracteres visibles."""
        if not self.pages:
            return False
        return self.visible_chars() >= min_chars_per_page * len(self.pages)


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


def extract_text(data: bytes) -> PdfText:
    pages: list[str] = []
    with open_pdf(data) as pdf:
        for i in range(len(pdf)):
            page = pdf[i]
            try:
                textpage = page.get_textpage()
                try:
                    pages.append(textpage.get_text_bounded().replace("\r\n", "\n").strip())
                finally:
                    textpage.close()
            finally:
                page.close()
    return PdfText(pages)
