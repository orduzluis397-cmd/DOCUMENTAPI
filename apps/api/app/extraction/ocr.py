"""OCR con Tesseract (`spa`) vía pytesseract, para imágenes y páginas escaneadas de PDF.

Si Tesseract no está instalado (ni en el PATH ni en `TESSERACT_CMD`), la ruta OCR queda
**no disponible**: `OcrUnavailableError` con un mensaje claro, sin intentar nada más.

Límites contra abuso (DoS): páginas/cuadros máximos, tope de píxeles por página (se baja la
escala antes de renderizar o se reduce la imagen), `timeout` por llamada a Tesseract y
`Image.MAX_IMAGE_PIXELS` explícito (Pillow corta las "bombas de descompresión").
"""

from __future__ import annotations

import io
import math
import os
import shutil
from dataclasses import dataclass, field
from typing import Any, Protocol

from PIL import Image

from app.extraction.types import ExtractionError

# Imagen más grande que Pillow acepta abrir; por encima del doble lanza DecompressionBombError.
MAX_IMAGE_PIXELS = 100_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


class OcrUnavailableError(ExtractionError):
    """Tesseract (o su idioma) no está instalado."""


class OcrEngine(Protocol):
    def image_to_text(self, image: Image.Image) -> str: ...


@dataclass(frozen=True)
class OcrLimits:
    max_pages: int = 10
    max_pixels: int = 25_000_000
    dpi: int = 300


@dataclass
class OcrResult:
    pages: list[str] = field(default_factory=list)
    omitted: list[int] = field(default_factory=list)  # páginas/cuadros (desde 1) sin OCR


_WINDOWS_DEFAULT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def tesseract_path(cmd: str | None = None) -> str | None:
    """Ruta del binario de Tesseract (`TESSERACT_CMD`, PATH o la ruta por defecto en Windows)."""
    if cmd:
        return shutil.which(cmd) or None
    return shutil.which("tesseract") or shutil.which(_WINDOWS_DEFAULT)


class TesseractOcr:
    def __init__(
        self,
        cmd: str | None = None,
        lang: str = "spa",
        tessdata_dir: str | None = None,
        timeout_s: int = 60,
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
        try:
            langs = set(pytesseract.get_languages(config=""))
        except Exception as exc:
            raise OcrUnavailableError(f"OCR no disponible: Tesseract no responde ({exc})") from exc
        if lang not in langs:
            raise OcrUnavailableError(
                f"OCR no disponible: falta el idioma '{lang}' de Tesseract (hay: {sorted(langs)})."
            )
        self._lang = lang
        self._timeout = timeout_s
        self._pytesseract = pytesseract

    def image_to_text(self, image: Image.Image) -> str:
        try:
            text: str = self._pytesseract.image_to_string(
                image, lang=self._lang, timeout=self._timeout
            )
        except RuntimeError as exc:  # pytesseract: "Tesseract process timeout"
            raise ExtractionError(f"OCR: Tesseract superó {self._timeout} s ({exc})") from exc
        return text.strip()


def fit_pixels(image: Image.Image, max_pixels: int) -> Image.Image:
    """Reduce la imagen si pasa de `max_pixels` (conserva la proporción)."""
    w, h = image.size
    if w * h <= max_pixels:
        return image
    ratio = math.sqrt(max_pixels / (w * h))
    return image.resize((max(1, int(w * ratio)), max(1, int(h * ratio))))


def render_scale(width_pt: float, height_pt: float, dpi: int, max_pixels: int) -> float:
    """Escala de render (pt → px) a `dpi`, bajada si la página pasaría de `max_pixels`."""
    scale = dpi / 72
    pixels = width_pt * scale * height_pt * scale
    if pixels > max_pixels:
        scale *= math.sqrt(max_pixels / pixels)
    return scale


def ocr_image(data: bytes, engine: OcrEngine, limits: OcrLimits | None = None) -> OcrResult:
    """Una entrada por cuadro (los TIFF pueden traer varias páginas), hasta `max_pages`."""
    limits = limits or OcrLimits()
    try:
        img = Image.open(io.BytesIO(data))
    except Image.DecompressionBombError as exc:
        raise ExtractionError(f"Imagen demasiado grande: {exc}") from exc
    except Exception as exc:
        raise ExtractionError(f"Imagen ilegible: {exc}") from exc
    result = OcrResult()
    with img:
        frames = getattr(img, "n_frames", 1)
        for frame in range(min(frames, limits.max_pages)):
            img.seek(frame)
            page = fit_pixels(img.convert("RGB"), limits.max_pixels)
            result.pages.append(engine.image_to_text(page))
        result.omitted = list(range(limits.max_pages + 1, frames + 1))
    return result


def ocr_pdf_page(page: Any, engine: OcrEngine, limits: OcrLimits) -> str:
    """Renderiza una página de pypdfium2 (con tope de píxeles) y le pasa OCR."""
    width, height = page.get_size()
    bitmap = page.render(scale=render_scale(width, height, limits.dpi, limits.max_pixels))
    try:
        return engine.image_to_text(bitmap.to_pil())
    finally:
        bitmap.close()
