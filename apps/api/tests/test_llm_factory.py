"""Construcción del cliente LLM por `.env` (sin red: construir no llama al proveedor)."""

from decimal import Decimal

import pytest

from app.config import Settings
from app.extraction.prompts import load_prompt
from app.llm.base import LLMNotConfiguredError, LLMUsage
from app.llm.factory import build_llm_client
from app.llm.pricing import ModelPrice, PriceTable


@pytest.mark.parametrize("provider", ["anthropic", "openai", "vllm"])
def test_missing_credentials_fail_clearly(provider: str) -> None:
    s = Settings(
        llm_provider=provider,  # type: ignore[arg-type]
        anthropic_api_key=None,
        openai_api_key=None,
        vllm_base_url=None,
    )
    with pytest.raises(LLMNotConfiguredError, match="Falta"):
        build_llm_client(s)


@pytest.mark.parametrize(
    ("provider", "extra"),
    [
        ("anthropic", {"anthropic_api_key": "clave-falsa"}),
        ("openai", {"openai_api_key": "clave-falsa"}),
        ("vllm", {"vllm_base_url": "http://127.0.0.1:1/v1"}),
    ],
)
def test_builds_each_provider(provider: str, extra: dict[str, str]) -> None:
    client = build_llm_client(Settings(llm_provider=provider, **extra))  # type: ignore[arg-type]
    assert client.provider == provider


def test_empty_env_values_mean_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MAX_COST_PER_DOC_USD", "")
    monkeypatch.setenv("LLM_MODEL_EXTRACTION", "  ")
    monkeypatch.setenv("TESSERACT_CMD", "")
    s = Settings()
    assert s.llm_max_cost_per_doc_usd is None
    assert s.llm_model_extraction is None
    assert s.tesseract_cmd is None
    monkeypatch.setenv("LLM_MAX_COST_PER_DOC_USD", "0.02")
    assert Settings().llm_max_cost_per_doc_usd == Decimal("0.02")


def test_price_table_cost_and_validity() -> None:
    table = PriceTable(
        precios=[
            ModelPrice(
                proveedor="anthropic",
                modelo="m",
                usd_por_millon_entrada=Decimal("3"),
                usd_por_millon_salida=Decimal("15"),
            )
        ]
    )
    cost = table.cost_usd("anthropic", "m", LLMUsage(input_tokens=2000, output_tokens=500))
    assert cost == Decimal("0.013500")
    with pytest.raises(LLMNotConfiguredError):
        table.cost_usd("anthropic", "otro", LLMUsage())


def test_prompts_are_versioned() -> None:
    for name in ("clasificacion", "extraccion"):
        prompt = load_prompt(name)
        assert prompt.version
    extraccion = load_prompt("extraccion")
    assert set(extraccion.tipos) == {"factura", "cuenta_cobro", "rut", "extracto", "contrato"}
    # El texto del documento se inserta tal cual, aunque traiga `$` o llaves.
    rendered = extraccion.render_user(tipo="factura", instrucciones="", texto="Total $ {x}")
    assert "Total $ {x}" in rendered
