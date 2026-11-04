"""Construcción del cliente LLM por `.env` (sin red: construir no llama al proveedor)."""

from decimal import Decimal

import pytest

from app.config import Settings
from app.extraction.prompts import load_prompt
from app.llm.base import LLMNotConfiguredError, LLMUsage
from app.llm.factory import build_llm_client, is_local_url
from app.llm.instructor_client import InstructorLLMClient
from app.llm.pricing import ModelPrice, PriceTable


@pytest.mark.parametrize("provider", ["anthropic", "openai", "vllm"])
def test_missing_credentials_fail_clearly(provider: str) -> None:
    s = Settings(
        llm_provider=provider,  # type: ignore[arg-type]
        anthropic_api_key=None,
        openai_api_key=None,
        vllm_base_url=None,
        llm_external_enabled=True,
    )
    with pytest.raises(LLMNotConfiguredError, match="Falta"):
        build_llm_client(s)


@pytest.mark.parametrize(
    ("provider", "extra", "param"),
    [
        ("anthropic", {"anthropic_api_key": "clave-falsa"}, "max_tokens"),
        ("openai", {"openai_api_key": "clave-falsa"}, "max_completion_tokens"),
        ("vllm", {"vllm_base_url": "http://127.0.0.1:1/v1"}, "max_tokens"),
    ],
)
def test_builds_each_provider_with_output_cap(
    provider: str, extra: dict[str, str], param: str
) -> None:
    settings = Settings(
        llm_provider=provider,  # type: ignore[arg-type]
        llm_external_enabled=True,
        llm_max_output_tokens=321,
        **extra,  # type: ignore[arg-type]
    )
    client = build_llm_client(settings)
    assert client.provider == provider
    assert isinstance(client, InstructorLLMClient)
    # El tope de salida llega a los 3 proveedores (con el nombre de parámetro de cada API).
    assert (client._max_tokens_param, client._max_output_tokens) == (param, 321)


def test_external_providers_disabled_by_default() -> None:
    assert Settings().llm_external_enabled is False
    for provider, extra in (
        ("anthropic", {"anthropic_api_key": "clave-falsa"}),
        ("openai", {"openai_api_key": "clave-falsa"}),
        ("vllm", {"vllm_base_url": "https://vllm.ejemplo.com/v1"}),
    ):
        s = Settings(llm_provider=provider, llm_external_enabled=False, **extra)  # type: ignore[arg-type]
        with pytest.raises(LLMNotConfiguredError, match="LLM_EXTERNAL_ENABLED=false"):
            build_llm_client(s)


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:8000/v1", "http://localhost:8000/v1", "http://192.168.1.20/v1"]
)
def test_local_vllm_allowed_without_external_flag(url: str) -> None:
    assert is_local_url(url)
    client = build_llm_client(
        Settings(llm_provider="vllm", vllm_base_url=url, llm_external_enabled=False)
    )
    assert client.provider == "vllm"


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
    rendered = extraccion.render_user(
        tipo="factura", instrucciones="", etiqueta="documento-abc", texto="Total $ {x}"
    )
    assert "Total $ {x}" in rendered
    assert "<documento-abc>" in rendered
    assert "</documento-abc>" in rendered
