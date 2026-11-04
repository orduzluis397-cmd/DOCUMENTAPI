"""Carga de prompts versionados (`app/prompts/*.yaml`, campo `version` obligatorio)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import Template

import yaml
from pydantic import BaseModel, ConfigDict, Field

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


class Prompt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    version: str = Field(min_length=1)
    system: str
    user: str
    tipos: dict[str, str] = Field(default_factory=dict)
    reintento: str | None = None

    def render_user(self, **values: str) -> str:
        # `Template.substitute`: el texto del documento se inserta tal cual (sus `$` o llaves no
        # se interpretan) y falta de variable = error.
        return Template(self.user).substitute(values)

    def render_retry(self, errores: str) -> str:
        if self.reintento is None:
            raise ValueError(f"El prompt {self.id} no define `reintento`")
        return Template(self.reintento).substitute(errores=errores)


@lru_cache
def load_prompt(name: str) -> Prompt:
    data = yaml.safe_load((PROMPTS_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
    return Prompt.model_validate(data)
