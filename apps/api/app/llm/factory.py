"""Construye el cliente LLM según `LLM_PROVIDER` (anthropic | openai | vllm).

Con `LLM_EXTERNAL_ENABLED=false` (por defecto) solo se construye un cliente vLLM cuya URL sea
de la propia máquina o de una red privada: ningún texto de documento sale a un proveedor externo.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from app.config import Settings
from app.llm.base import LLMClient, LLMNotConfiguredError
from app.llm.instructor_client import InstructorLLMClient

_LOCAL_HOSTS = {"localhost"}


def is_local_url(url: str) -> bool:
    """`True` si el host es loopback o de red privada (vLLM propio)."""
    host = (urlparse(url).hostname or "").lower()
    if host in _LOCAL_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


def _require_external(settings: Settings, provider: str) -> None:
    if not settings.llm_external_enabled:
        raise LLMNotConfiguredError(
            f"LLM_EXTERNAL_ENABLED=false: no se envían documentos a un proveedor externo "
            f"({provider}). Solo se admite vLLM local hasta que el usuario lo autorice."
        )


def build_llm_client(settings: Settings) -> LLMClient:
    """Cliente real del proveedor (no llama a la red al construirse).

    Sin clave, sin URL o sin permiso para proveedores externos lanza `LLMNotConfiguredError`.
    """
    import instructor

    # SDK de proveedores importados solo al construir el cliente (el worker arranca sin ellos).
    provider = settings.llm_provider
    max_out = settings.llm_max_output_tokens
    if provider == "anthropic":
        _require_external(settings, provider)
        if settings.anthropic_api_key is None:
            raise LLMNotConfiguredError("Falta ANTHROPIC_API_KEY (LLM_PROVIDER=anthropic).")
        import anthropic

        client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key.get_secret_value(),
            timeout=settings.llm_timeout_s,
            max_retries=0,
        )
        return InstructorLLMClient(
            provider, instructor.from_anthropic(client), max_output_tokens=max_out
        )

    import openai

    if provider == "openai":
        _require_external(settings, provider)
        if settings.openai_api_key is None:
            raise LLMNotConfiguredError("Falta OPENAI_API_KEY (LLM_PROVIDER=openai).")
        oa = openai.OpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.llm_timeout_s,
            max_retries=0,
        )
        # La API de OpenAI usa max_completion_tokens (max_tokens está en desuso).
        return InstructorLLMClient(
            provider,
            instructor.from_openai(oa),
            max_output_tokens=max_out,
            max_tokens_param="max_completion_tokens",
        )

    # vllm: servidor propio compatible con OpenAI (fase 4).
    if not settings.vllm_base_url:
        raise LLMNotConfiguredError("Falta VLLM_BASE_URL (LLM_PROVIDER=vllm).")
    if not is_local_url(settings.vllm_base_url):
        _require_external(settings, f"vllm en {urlparse(settings.vllm_base_url).hostname}")
    key = settings.vllm_api_key.get_secret_value() if settings.vllm_api_key else "sin-clave"
    oa = openai.OpenAI(
        api_key=key,
        base_url=settings.vllm_base_url,
        timeout=settings.llm_timeout_s,
        max_retries=0,
    )
    return InstructorLLMClient(provider, instructor.from_openai(oa), max_output_tokens=max_out)
