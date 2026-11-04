"""Catálogos con vigencia usados por los esquemas (regla dura 8: nada de constantes cerradas).

Las responsabilidades de la casilla 53 del RUT **no** son un ``Enum``: la DIAN crea y retira
códigos (el 09 se retiró de oficio, pero los RUT antiguos lo muestran). El esquema acepta cualquier
código de dos dígitos y el validador consulta este catálogo con la fecha del documento.

Este catálogo es provisional en código; pasará a una tabla con ``vigente_desde``/``vigente_hasta``
cuando exista la base de datos. Fuente: ``docs/glosario.md`` §5 (pendiente de validar con el
contador asesor; las entradas con ``verificar=True`` no deben usarse para decidir retenciones).
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


class ResponsabilidadRUT(BaseModel):
    model_config = ConfigDict(frozen=True)

    codigo: str
    nombre: str
    vigente_desde: date | None = None
    vigente_hasta: date | None = None
    retirado: bool = False
    verificar: bool = False
    fuente: str = "docs/glosario.md"

    def vigente_en(self, fecha: date | None) -> bool:
        """``False`` si está retirado (sin fecha conocida) o fuera de su vigencia en ``fecha``."""
        if self.retirado and self.vigente_hasta is None:
            return False
        if fecha is None:
            return not self.retirado
        if self.vigente_desde is not None and fecha < self.vigente_desde:
            return False
        return self.vigente_hasta is None or fecha <= self.vigente_hasta


RESPONSABILIDADES_RUT: tuple[ResponsabilidadRUT, ...] = (
    ResponsabilidadRUT(codigo="05", nombre="Impuesto de renta y complementarios régimen ordinario"),
    ResponsabilidadRUT(codigo="07", nombre="Retención en la fuente a título de renta"),
    # Retirada de oficio por la DIAN; fecha exacta por confirmar [verificar].
    ResponsabilidadRUT(
        codigo="09",
        nombre="Retención en la fuente en el impuesto sobre las ventas",
        retirado=True,
        verificar=True,
    ),
    ResponsabilidadRUT(codigo="13", nombre="Gran contribuyente"),
    ResponsabilidadRUT(codigo="14", nombre="Informante de exógena"),
    ResponsabilidadRUT(codigo="15", nombre="Autorretenedor"),
    ResponsabilidadRUT(codigo="42", nombre="Obligado a llevar contabilidad", verificar=True),
    ResponsabilidadRUT(codigo="47", nombre="Régimen Simple de Tributación (SIMPLE)"),
    ResponsabilidadRUT(codigo="48", nombre="Impuesto sobre las ventas (IVA)"),
    ResponsabilidadRUT(codigo="49", nombre="No responsable de IVA"),
    ResponsabilidadRUT(codigo="52", nombre="Facturador electrónico"),
)


def buscar_responsabilidad(
    codigo: str, catalogo: tuple[ResponsabilidadRUT, ...] = RESPONSABILIDADES_RUT
) -> ResponsabilidadRUT | None:
    return next((r for r in catalogo if r.codigo == codigo), None)
