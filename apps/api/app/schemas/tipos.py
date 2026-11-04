"""Tipos comunes de los esquemas de extracción (INSTRUCCIONES.md §8.2, evals/datasets/GUIA.md).

Normalización en la frontera:

- Montos: ``Decimal`` con punto decimal, sin separador de miles, hasta 2 decimales. Se rechaza
  ``"119.000"`` o ``"1,5"``: son ambiguos (¿miles o decimales?) y un error silencioso ahí es un
  error contable.
- NIT: solo dígitos, sin puntos ni DV (el DV va en su propio campo). Se quitan puntos, comas y
  espacios; un guion (``900123456-8``) se rechaza para no mezclar el DV en el número.
- CUFE: minúsculas y sin espacios. Su forma (96 hex) la revisa el validador de dominio, no el
  esquema, para no perder el documento entero por un CUFE mal leído.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import AfterValidator, BeforeValidator, Field

_MONTO_TEXTO = re.compile(r"^-?\d+(?:\.\d{1,2})?$")
_MONTO_AMBIGUO = re.compile(r"^-?\d{1,3}(?:\.\d{3})+$")
_NIT_LIMPIO = re.compile(r"^[1-9]\d{4,14}$")


def _a_decimal(valor: Any, decimales: int) -> Any:
    """Convierte str/int/float a ``Decimal`` sin aceptar separadores de miles."""
    if isinstance(valor, bool):
        raise ValueError("un monto no puede ser booleano")
    if isinstance(valor, float):
        valor = Decimal(repr(valor))
    elif isinstance(valor, int):
        valor = Decimal(valor)
    elif isinstance(valor, str):
        texto = valor.strip()
        if _MONTO_AMBIGUO.match(texto) and decimales == 2:
            raise ValueError(
                f"monto ambiguo {texto!r}: usa punto decimal y sin separador de miles "
                "(p. ej. 119000.00)"
            )
        if decimales == 2 and not _MONTO_TEXTO.match(texto):
            raise ValueError(
                f"monto inválido {texto!r}: dígitos con punto decimal y hasta 2 decimales"
            )
        try:
            valor = Decimal(texto)
        except InvalidOperation as exc:
            raise ValueError(f"número inválido {texto!r}") from exc
    return valor


def _monto(valor: Any) -> Any:
    return _a_decimal(valor, 2)


def _cantidad(valor: Any) -> Any:
    return _a_decimal(valor, 6)


Monto = Annotated[
    Decimal,
    BeforeValidator(_monto),
    Field(max_digits=18, decimal_places=2, allow_inf_nan=False),
]
"""Monto en pesos: hasta 2 decimales; puede ser negativo (débitos de un extracto)."""

MontoNoNegativo = Annotated[Monto, Field(ge=0)]
"""Monto de factura, cuenta de cobro o contrato."""

Cantidad = Annotated[
    Decimal,
    BeforeValidator(_cantidad),
    Field(max_digits=24, decimal_places=6, allow_inf_nan=False),
]
"""Cantidades, precios unitarios y tarifas (hasta 6 decimales, como admite UBL)."""


def _limpiar_nit(valor: Any) -> Any:
    if isinstance(valor, int) and not isinstance(valor, bool):
        valor = str(valor)
    if isinstance(valor, str):
        texto = valor.strip()
        if "-" in texto:
            raise ValueError("el NIT va sin DV: pon el dígito de verificación en su campo dv_*")
        return re.sub(r"[.,\s]", "", texto)
    return valor


def _verificar_nit(valor: str) -> str:
    if not _NIT_LIMPIO.match(valor):
        raise ValueError("NIT/cédula: de 5 a 15 dígitos, sin puntos ni DV, sin cero inicial")
    return valor


Nit = Annotated[str, BeforeValidator(_limpiar_nit), AfterValidator(_verificar_nit)]
"""NIT o cédula (NIT de persona natural, longitud variable), solo dígitos y sin DV."""

Dv = Annotated[int, Field(ge=0, le=9)]
"""Dígito de verificación del NIT."""


def _normalizar_cufe(valor: Any) -> Any:
    if isinstance(valor, str):
        return re.sub(r"\s", "", valor).lower()
    return valor


Cufe = Annotated[str, BeforeValidator(_normalizar_cufe)]
"""CUFE/CUDE en minúsculas; el validador de dominio exige 96 hex."""

TextoNoVacio = Annotated[str, Field(min_length=1)]
