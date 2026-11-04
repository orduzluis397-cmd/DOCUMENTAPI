"""OCR con Tesseract (`spa`) vía pytesseract, para imágenes y PDF escaneados.

Si Tesseract no está instalado (ni en el PATH ni en `TESSERACT_CMD`), la ruta OCR queda
**no disponible**: `OcrUnavailableError` con un mensaje claro, sin intentar nada más.
"""

from __future__ import annotations

import io
import os
import shutil
from typing import Protocol

from PIL import Image

from app.extraction.pdf_text import open_pdf
from app.extraction.types import ExtractionError


class OcrUnavailableError(ExtractionError):
    """Tesseract (o su idioma) no está instalado."""


class OcrEngine(Protocol):
    def image_to_text(self, image: Image.Image) -> str: ...


_WINDOWS_DEFAULT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def tesseract_path(cmd: str | None = None) -> str | None:
    """Ruta del binario de Tesseract (`TESSERACT_CMD`, PATH o la ruta por defecto en Windows)."""
    if cmd:
        return shutil.which(cmd) or None
    return shutil.which("tesseract") or shutil.which(_WINDOWS_DEFAULT)


class TesseractOcr:
    def __init__(
        self, cmd: str | None = None, lang: str = "spa", tessdata_dir: str | None = None
    ) -> None:
        path = tesseract_path(cmd)
        if path is None:
            raise OcrUnavailableError(
                "OCR no disponible: Tesseract no está instalado. Instálalo con el idioma 'spa' "
                "y, si no está en el PATH, indica la ruta en TESSERACT_CMD."
            )
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = path
        if tessdata_dir:
            # Por variable de entorno y no `--tessdata-dir`: pytesseract parte `config` con
            # shlex en modo no-POSIX en Windows y las comillas de una ruta con espacios llegan
            # literales a Tesseract. El proceso hijo hereda la variable.
            os.environ["TESSDATA_PREFIX"] = tessdata_dir
        self._config = ""
        try:
            langs = set(pytesseract.get_languages(config=self._config))
        except Exception as exc:
            raise OcrUnavailableError(f"OCR no disponible: Tesseract no responde ({exc})") from exc
        if lang not in langs:
            raise OcrUnavailableError(
                f"OCR no disponible: falta el idioma '{lang}' de Tesseract (hay: {sorted(langs)})."
            )
        self._lang = lang
        self._pytesseract = pytesseract

    def image_to_text(self, image: Image.Image) -> str:
        text: str = self._pytesseract.image_to_string(image, lang=self._lang, config=self._config)
        return text.strip()


def ocr_image(data: bytes, engine: OcrEngine) -> list[str]:
    """Una entrada por cuadro (los TIFF pueden traer varias páginas)."""
    try:
        img = Image.open(io.BytesIO(data))
    except Exception as exc:
        raise ExtractionError(f"Imagen ilegible: {exc}") from exc
    pages: list[str] = []
    with img:
        for frame in range(getattr(img, "n_frames", 1)):
            img.seek(frame)
            pages.append(engine.image_to_text(img.convert("RGB")))
    return pages


def ocr_pdf(data: bytes, engine: OcrEngine, dpi: int = 300, max_pages: int = 10) -> list[str]:
    """Renderiza cada página con pypdfium2 y le pasa OCR."""
    pages: list[str] = []
    with open_pdf(data) as pdf:
        for i in range(min(len(pdf), max_pages)):
            page = pdf[i]
            try:
                bitmap = page.render(scale=dpi / 72)
                try:
                    image = bitmap.to_pil()
                    pages.append(engine.image_to_text(image))
                finally:
                    bitmap.close()
            finally:
                page.close()
    return pages
