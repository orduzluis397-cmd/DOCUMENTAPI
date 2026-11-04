"""Construye el cliente LLM según `LLM_PROVIDER` (anthropic | openai | vllm)."""

from __future__ import annotations

from app.config import Settings
from app.llm.base import LLMClient, LLMNotConfiguredError
from app.llm.instructor_client import InstructorLLMClient


def build_llm_client(settings: Settings) -> LLMClient:
    """Cliente real del proveedor (no llama a la red al construirse).

    Sin clave o URL lanza `LLMNotConfiguredError`.
    """
    import instructor

    # SDK de proveedores importados solo al construir el cliente (el worker arranca sin ellos).
    provider = settings.llm_provider
    if provider == "anthropic":
        if settings.anthropic_api_key is None:
            raise LLMNotConfiguredError("Falta ANTHROPIC_API_KEY (LLM_PROVIDER=anthropic).")
        import anthropic

        client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key.get_secret_value(),
            timeout=settings.llm_timeout_s,
            max_retries=0,
        )
        return InstructorLLMClient(
            provider,
            instructor.from_anthropic(client),
            max_output_tokens=settings.llm_max_output_tokens,
        )

    import openai

    if provider == "openai":
        if settings.openai_api_key is None:
            raise LLMNotConfiguredError("Falta OPENAI_API_KEY (LLM_PROVIDER=openai).")
        oa = openai.OpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.llm_timeout_s,
            max_retries=0,
        )
    else:  # vllm: servidor propio compatible con OpenAI (fase 4)
        if not settings.vllm_base_url:
            raise LLMNotConfiguredError("Falta VLLM_BASE_URL (LLM_PROVIDER=vllm).")
        key = settings.vllm_api_key.get_secret_value() if settings.vllm_api_key else "sin-clave"
        oa = openai.OpenAI(
            api_key=key,
            base_url=settings.vllm_base_url,
            timeout=settings.llm_timeout_s,
            max_retries=0,
        )
    return InstructorLLMClient(provider, instructor.from_openai(oa))
