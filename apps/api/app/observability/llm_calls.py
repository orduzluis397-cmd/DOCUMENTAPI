"""Registro de cada llamada LLM en `llm_calls` y tope de costo por documento (regla dura 9).

`TrackedLLM` envuelve un `LLMClient` para UN documento:

- Antes de llamar: exige precio conocido del modelo y que lo gastado no haya alcanzado el tope
  (`LLM_MAX_COST_PER_DOC_USD`); si lo alcanzó, lanza `CostCapExceededError` sin llamar.
- Después: escribe la fila de `llm_calls` (modelo, tokens, costo USD, latencia ms, `trace_id`,
  `document_id`) en su **propia transacción** bajo RLS, para que quede aunque la extracción falle
  después. Los errores del proveedor también se registran (`status='error'`).
- Si una llamada deja el gasto por encima del tope, `cap_exceeded` queda en `True`: la respuesta
  se puede usar, pero no habrá más llamadas y el documento va a revisión humana.
"""

from __future__ import annotations

import time
import uuid
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import LlmCall
from app.db.session import tenant_session
from app.llm.base import LLMClient, LLMError, LLMUsage, Message, StructuredResult
from app.llm.pricing import PriceTable


class CostCapExceededError(Exception):
    """El documento alcanzó su tope de costo LLM: no se hacen más llamadas."""


class TrackedLLM:
    def __init__(
        self,
        client: LLMClient,
        prices: PriceTable,
        *,
        organization_id: uuid.UUID,
        document_id: uuid.UUID | None,
        trace_id: str,
        max_cost_usd: Decimal,
        factory: sessionmaker[Session] | None = None,
    ) -> None:
        self._client = client
        self._prices = prices
        self._org = organization_id
        self._doc = document_id
        self._factory = factory
        self.trace_id = trace_id
        self.max_cost_usd = max_cost_usd
        self.spent_usd = Decimal(0)
        self.calls = 0

    @property
    def provider(self) -> str:
        return self._client.provider

    @property
    def cap_exceeded(self) -> bool:
        return self.spent_usd > self.max_cost_usd

    def structured[T: BaseModel](
        self,
        *,
        purpose: str,
        prompt_version: str,
        model: str,
        messages: list[Message],
        response_model: type[T],
    ) -> StructuredResult[T]:
        if self.spent_usd >= self.max_cost_usd:
            raise CostCapExceededError(
                f"Tope de costo por documento alcanzado: US${self.spent_usd} de "
                f"US${self.max_cost_usd}"
            )
        self._prices.price(self.provider, model)  # sin precio no se llama (falla cerrado)
        start = time.perf_counter()
        try:
            result = self._client.structured(
                model=model, messages=messages, response_model=response_model
            )
        except LLMError as exc:
            self._record(purpose, prompt_version, model, LLMUsage(), _ms(start), "error", str(exc))
            raise
        error = None
        if result.value is None:
            error = f"salida no valida el esquema: {result.validation_error}"[:4000]
        self._record(purpose, prompt_version, model, result.usage, _ms(start), "ok", error)
        return result

    def _record(
        self,
        purpose: str,
        prompt_version: str,
        model: str,
        usage: LLMUsage,
        latency_ms: int,
        status: str,
        error: str | None,
    ) -> None:
        cost = self._prices.cost_usd(self.provider, model, usage)
        self.spent_usd += cost
        self.calls += 1
        with tenant_session(self._org, self._factory) as session:
            session.add(
                LlmCall(
                    organization_id=self._org,
                    document_id=self._doc,
                    provider=self.provider,
                    model=model,
                    purpose=purpose,
                    prompt_version=prompt_version,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cost_usd=cost,
                    latency_ms=latency_ms,
                    trace_id=self.trace_id,
                    status=status,
                    error=error,
                )
            )
            session.commit()


def _ms(start: float) -> int:
    return max(0, round((time.perf_counter() - start) * 1000))
