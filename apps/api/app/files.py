"""Validación de archivos subidos: tipo REAL por firma (bytes iniciales) y tamaño máximo.

No se confía en la extensión ni en el `Content-Type` que manda el cliente.
"""

from dataclasses import dataclass

# Tipos que el enrutador de extracción sabrá procesar (§8.3): PDF, imágenes escaneadas y XML
# de factura electrónica DIAN.
ALLOWED_TYPES: dict[str, str] = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/tiff": ".tif",
    "application/xml": ".xml",
}

_UTF8_BOM = b"\xef\xbb\xbf"


class InvalidFileError(ValueError):
    """El archivo no es de un tipo permitido o excede el tamaño."""


@dataclass(frozen=True, slots=True)
class DetectedType:
    content_type: str
    extension: str


def sniff(data: bytes) -> str | None:
    """Devuelve el tipo MIME según la firma del contenido, o None si no es un tipo permitido."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    head = data.removeprefix(_UTF8_BOM).lstrip()[:5]
    if head.startswith(b"<?xml") or (head.startswith(b"<") and _looks_like_xml(data)):
        return "application/xml"
    return None


def _looks_like_xml(data: bytes) -> bool:
    # Sin declaración <?xml: se acepta si es texto UTF-8 que empieza por una etiqueta.
    try:
        text = data[:4096].decode("utf-8")
    except UnicodeDecodeError:
        return False
    stripped = text.lstrip("﻿").lstrip()
    return len(stripped) > 1 and (stripped[1].isalpha() or stripped[1] in "_!")


def validate(data: bytes, max_bytes: int) -> DetectedType:
    if not data:
        raise InvalidFileError("El archivo está vacío.")
    if len(data) > max_bytes:
        raise InvalidFileError(f"El archivo supera el máximo de {max_bytes // (1024 * 1024)} MB.")
    content_type = sniff(data)
    if content_type is None:
        raise InvalidFileError(
            "Tipo de archivo no permitido (se aceptan PDF, PNG, JPEG, TIFF, XML)."
        )
    return DetectedType(content_type=content_type, extension=ALLOWED_TYPES[content_type])
