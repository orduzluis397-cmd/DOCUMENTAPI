"""Cliente LLM falso SIN RED y OCR falso.

`scripted_llm` construye el cliente real de la app (`InstructorLLMClient` sobre el SDK de
OpenAI con Instructor) pero con un transporte HTTP simulado (`httpx2.MockTransport`; httpx2 es
el cliente HTTP del SDK de OpenAI 3.x): ninguna petición sale de la máquina. Cada respuesta
es el JSON que el "modelo" devuelve como llamada a herramienta, elegido por el nombre del
esquema pedido (`Clasificacion`, `CuentaCobro`, …).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx2
import instructor
import openai
from PIL import Image

from app.llm.instructor_client import InstructorLLMClient
from app.llm.pricing import ModelPrice, PriceTable

FAKE_MODEL = "modelo-falso"
FAKE_PROVIDER = "openai"
INPUT_TOKENS = 1000
OUTPUT_TOKENS = 200
# 1000 x 1 USD/M + 200 x 5 USD/M = 0.002 USD por llamada.
COST_PER_CALL = Decimal("0.002000")

FAKE_PRICES = PriceTable(
    precios=[
        ModelPrice(
            proveedor=FAKE_PROVIDER,
            modelo=FAKE_MODEL,
            usd_por_millon_entrada=Decimal("1"),
            usd_por_millon_salida=Decimal("5"),
        )
    ]
)


@dataclass
class ScriptedTransport:
    """Respuestas por nombre de herramienta, consumidas en orden (la última se repite)."""

    script: dict[str, list[dict[str, Any]]]
    requests: list[dict[str, Any]] = field(default_factory=list)
    fail_with: int | None = None

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        if self.fail_with is not None:
            return httpx2.Response(self.fail_with, json={"error": {"message": "falla simulada"}})
        tool = body["tools"][0]["function"]["name"]
        queue = self.script[tool]
        args = queue.pop(0) if len(queue) > 1 else queue[0]
        return httpx2.Response(
            200,
            json={
                "id": f"fake-{len(self.requests)}",
                "object": "chat.completion",
                "created": 0,
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {"name": tool, "arguments": json.dumps(args)},
                                }
                            ],
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": INPUT_TOKENS,
                    "completion_tokens": OUTPUT_TOKENS,
                    "total_tokens": INPUT_TOKENS + OUTPUT_TOKENS,
                },
            },
        )

    def tools_called(self) -> list[str]:
        return [r["tools"][0]["function"]["name"] for r in self.requests]


def scripted_llm(transport: ScriptedTransport) -> InstructorLLMClient:
    oa = openai.OpenAI(
        api_key="clave-falsa",
        base_url="http://llm-falso.invalid/v1",
        http_client=httpx2.Client(transport=httpx2.MockTransport(transport)),
        max_retries=0,
    )
    return InstructorLLMClient(FAKE_PROVIDER, instructor.from_openai(oa))


class FakeOcr:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def image_to_text(self, image: Image.Image) -> str:
        self.calls += 1
        return self.text


def fake_ocr_factory(text: str) -> Callable[[], FakeOcr]:
    engine = FakeOcr(text)
    return lambda: engine
