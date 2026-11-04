"""Aplanado de documentos a `extracted_fields`, rescate de salidas inválidas y campos dudosos."""

from __future__ import annotations

import copy
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ValidationError

from app.extraction.types import Documento, FieldValue
from app.schemas.validators import ResultadoValidacion

_MAX_SALVAGE_ROUNDS = 100


class _ListChanged(Exception):  # noqa: N818 - señal interna, no un error
    """Se quitó un elemento de una lista: los índices de los demás errores cambiaron."""


def flatten(doc: Documento) -> list[tuple[str, Any]]:
    """`[("numero", "SETP1"), ("lineas[0].cantidad", "2"), …]` en el orden del esquema.

    Listas de objetos → un campo por hoja (`lineas[i].campo`); lista vacía → un campo con `[]`.
    Listas de textos (responsabilidades, actividades) → un solo campo con la lista.
    """
    data = doc.model_dump(mode="json", exclude={"tipo_documento"})
    out: list[tuple[str, Any]] = []
    for key, value in data.items():
        if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
            for i, item in enumerate(value):
                out.extend((f"{key}[{i}].{k}", v) for k, v in item.items())
        else:
            out.append((key, value))
    return out


def failed_fields(validaciones: Iterable[ResultadoValidacion]) -> set[str]:
    """Campos de las reglas de severidad `error` que fallaron."""
    return {
        campo for v in validaciones if not v.ok and v.severidad == "error" for campo in v.campos
    }


def in_scope(path: str, prefixes: Iterable[str]) -> bool:
    """`lineas[0].iva` está en el alcance de `lineas`; `nit_emisor` en el de `nit_emisor`."""
    return any(path == p or path.startswith((p + "[", p + ".")) for p in prefixes)


def to_field_values(doc: Documento, doubtful: Iterable[str]) -> list[FieldValue]:
    marks = set(doubtful)
    return [FieldValue(name, value, in_scope(name, marks)) for name, value in flatten(doc)]


def _path(loc: tuple[int | str, ...]) -> str:
    out = ""
    for part in loc:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out


def salvage[D: BaseModel](
    model: type[D], raw: dict[str, Any] | None, doc_type: str
) -> tuple[D | None, dict[str, Any]]:
    """Valida `raw` anulando los campos que no pasan el esquema.

    Devuelve el documento (o `None` si no se puede rescatar) y `{ruta: valor_original}` de los
    campos anulados, que se marcan como dudosos. No inventa valores: solo pone `None`.
    """
    if raw is None:
        return None, {}
    data = copy.deepcopy(raw)
    data["tipo_documento"] = doc_type
    removed: dict[str, Any] = {}
    for _ in range(_MAX_SALVAGE_ROUNDS):
        try:
            return model.model_validate(data), removed
        except ValidationError as exc:
            progressed = False
            try:
                for err in exc.errors():
                    loc = tuple(err["loc"])
                    if not loc or loc == ("tipo_documento",):
                        continue
                    if _null_out(data, loc, err["type"], removed):
                        progressed = True
            except _ListChanged:
                progressed = True
            if not progressed:
                return None, removed
    return None, removed


def _null_out(
    data: dict[str, Any], loc: tuple[int | str, ...], err_type: str, removed: dict[str, Any]
) -> bool:
    parent: Any = data
    for part in loc[:-1]:
        try:
            parent = parent[part]
        except (KeyError, IndexError, TypeError):
            return False
    last = loc[-1]
    try:
        original = parent[last]
    except (KeyError, IndexError, TypeError):
        return False
    if isinstance(parent, dict) and err_type == "extra_forbidden":
        del parent[last]  # campo inventado que el esquema no tiene: se descarta
        return True
    if isinstance(parent, list) and isinstance(last, int):
        # Elemento de una lista de textos/objetos que no valida: se quita de la lista. Los
        # índices de los demás errores de esta ronda ya no sirven: se revalida antes de seguir.
        removed.setdefault(_path(loc[:-1]), copy.deepcopy(parent))
        del parent[last]
        raise _ListChanged
    if original is None:
        if isinstance(parent, dict):
            del parent[last]  # el campo no admite null (p. ej. una lista): vale su defecto
            return True
        return False
    removed[_path(loc)] = original
    parent[last] = None
    return True
