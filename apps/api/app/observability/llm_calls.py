"""Registro de cada llamada LLM en `llm_calls`, tope por documento y presupuesto (reglas 9 y 10).

`TrackedLLM` envuelve un `LLMClient` para UN documento:

- Lo gastado arranca con la suma de `llm_calls` del documento: una reentrega del worker no
  reinicia el tope.
- Antes de cada llamada estima el peor costo (entrada aproximada por caracteres + todo
  `max_output_tokens`) y la rechaza si con ella se pasaría del tope por documento
  (`LLM_MAX_COST_PER_DOC_USD`) o del presupuesto global diario o mensual
  (`LLM_DAILY_BUDGET_USD`, `LLM_MONTHLY_BUDGET_USD`, sumando `llm_calls` de todas las
  organizaciones con `llm_spend_usd_since`). Un modelo sin precio no se llama.
- Después escribe la fila de `llm_calls` (modelo, tokens, costo USD, latencia ms, `trace_id`,
  `document_id`) en su **propia transacción** bajo RLS, para que quede aunque la extracción falle
  después. Los errores del proveedor también se registran (`status='error'`).
"""

from __future__ import annotations

import json
import math
import time
import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import LlmCall
from app.db.session import tenant_session
from app.llm.base import LLMClient, LLMError, LLMUsage, Message, StructuredResult
from app.llm.pricing import PriceTable

# Colombia no tiene horario de verano: UTC-5 fijo (sin depender de tzdata en Windows).
BOGOTA = timezone(timedelta(hours=-5), "America/Bogota")
# Estimación conservadora de tokens de entrada: ~3 caracteres por token en español.
_CHARS_PER_TOKEN = 3


class CostCapExceededError(Exception):
    """El documento alcanzó (o alcanzaría) su tope de costo: no se hacen más llamadas."""


class BudgetExceededError(CostCapExceededError):
    """La llamada pasaría el presupuesto global diario o mensual."""


def bogota_now() -> datetime:
    return datetime.now(UTC).astimezone(BOGOTA)


def estimate_input_tokens(messages: list[Message], response_model: type[BaseModel]) -> int:
    chars = sum(len(m.content) for m in messages)
    chars += len(json.dumps(response_model.model_json_schema(), ensure_ascii=False))
    return math.ceil(chars / _CHARS_PER_TOKEN)


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
        daily_budget_usd: Decimal,
        monthly_budget_usd: Decimal,
        max_output_tokens: int,
        factory: sessionmaker[Session] | None = None,
    ) -> None:
        self._client = client
        self._prices = prices
        self._org = organization_id
        self._doc = document_id
        self._factory = factory
        self.trace_id = trace_id
        self.max_cost_usd = max_cost_usd
        self.daily_budget_usd = daily_budget_usd
        self.monthly_budget_usd = monthly_budget_usd
        self.max_output_tokens = max_output_tokens
        self.calls = 0
        self.spent_usd = self._document_spend()

    @property
    def provider(self) -> str:
        return self._client.provider

    @property
    def cap_exceeded(self) -> bool:
        return self.spent_usd > self.max_cost_usd

    # ------------------------------------------------------------------ consultas de gasto

    def _document_spend(self) -> Decimal:
        if self._doc is None:
            return Decimal(0)
        with tenant_session(self._org, self._factory) as session:
            total = session.scalar(
                select(func.coalesce(func.sum(LlmCall.cost_usd), 0)).where(
                    LlmCall.document_id == self._doc
                )
            )
            session.commit()
        return Decimal(total or 0)

    def _global_spend_since(self, since: datetime) -> Decimal:
        with tenant_session(self._org, self._factory) as session:
            total = session.scalar(text("SELECT llm_spend_usd_since(:since)"), {"since": since})
            session.commit()
        return Decimal(total or 0)

    def _check_limits(self, estimate: Decimal, now: datetime) -> None:
        if self.spent_usd + estimate > self.max_cost_usd:
            raise CostCapExceededError(
                f"Tope de costo por documento: gastado US${self.spent_usd} + estimado "
                f"US${estimate} superaría US${self.max_cost_usd}"
            )
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        daily = self._global_spend_since(day_start)
        if daily + estimate > self.daily_budget_usd:
            raise BudgetExceededError(
                f"Presupuesto diario LLM: US${daily} + estimado US${estimate} superaría "
                f"US${self.daily_budget_usd}"
            )
        monthly = self._global_spend_since(day_start.replace(day=1))
        if monthly + estimate > self.monthly_budget_usd:
            raise BudgetExceededError(
                f"Presupuesto mensual LLM: US${monthly} + estimado US${estimate} superaría "
                f"US${self.monthly_budget_usd}"
            )

    # ------------------------------------------------------------------ llamada

    def structured[T: BaseModel](
        self,
        *,
        purpose: str,
        prompt_version: str,
        model: str,
        messages: list[Message],
        response_model: type[T],
    ) -> StructuredResult[T]:
        now = bogota_now()
        dia = now.date()
        # Sin precio vigente no se llama (falla cerrado); el peor caso usa todo max_output.
        estimate = self._prices.cost_usd(
            self.provider,
            model,
            LLMUsage(estimate_input_tokens(messages, response_model), self.max_output_tokens),
            dia,
        )
        self._check_limits(estimate, now)
        start = time.perf_counter()
        try:
            result = self._client.structured(
                model=model, messages=messages, response_model=response_model
            )
        except LLMError as exc:
            self._record(
                purpose, prompt_version, model, LLMUsage(), _ms(start), "error", str(exc), dia
            )
            raise
        error = None
        if result.value is None:
            error = f"salida no valida el esquema: {result.validation_error}"[:4000]
        self._record(purpose, prompt_version, model, result.usage, _ms(start), "ok", error, dia)
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
        dia: date,
    ) -> None:
        cost = self._prices.cost_usd(self.provider, model, usage, dia)
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
