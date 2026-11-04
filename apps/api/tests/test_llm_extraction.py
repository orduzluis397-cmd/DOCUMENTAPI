"""Clasificación y extracción con LLM falso (sin red), registro en `llm_calls` y tope de costo.

El "modelo" es `tests.fakes.scripted_llm`: el SDK real de OpenAI + Instructor sobre un transporte
HTTP simulado que devuelve JSON. Las filas de `llm_calls` se escriben en `contable_ia_test`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import LlmCall
from app.extraction.llm_extract import Clasificacion, classify
from app.extraction.router import RouterConfig, extract_document
from app.extraction.types import ExtractionOutcome
from app.llm.base import EXTRACTION_TEMPERATURE, LLMNotConfiguredError
from app.llm.pricing import PriceTable
from app.observability.llm_calls import CostCapExceededError, TrackedLLM
from tests.conftest import Tenant
from tests.docs_fixtures import CUENTA_COBRO_LINES, HOY, cuenta_cobro_json, text_pdf
from tests.fakes import (
    COST_PER_CALL,
    FAKE_MODEL,
    FAKE_PRICES,
    ScriptedTransport,
    scripted_llm,
)

PDF = text_pdf(CUENTA_COBRO_LINES)
CLASIFICA = {"Clasificacion": [{"tipo_documento": "cuenta_cobro"}]}


def _run(
    transport: ScriptedTransport,
    tenant: Tenant,
    factory: sessionmaker[Session],
    *,
    cap: str = "0.05",
    retries: int = 1,
    trace_id: str = "trace-llm",
) -> tuple[ExtractionOutcome, TrackedLLM]:
    tracked = TrackedLLM(
        scripted_llm(transport),
        FAKE_PRICES,
        organization_id=tenant.org_id,
        document_id=tenant.document_id,
        trace_id=trace_id,
        max_cost_usd=Decimal(cap),
        factory=factory,
    )
    out = extract_document(
        PDF,
        config=RouterConfig(model_extraction=FAKE_MODEL, max_retries=retries),
        llm_factory=lambda: tracked,
        ocr_factory=lambda: pytest.fail("un PDF con texto no pasa por OCR"),
        trace_id=trace_id,
        hoy=HOY,
    )
    return out, tracked


def _calls(owner_engine: Engine, trace_id: str) -> list[LlmCall]:
    with Session(owner_engine) as s:
        return list(
            s.scalars(
                select(LlmCall).where(LlmCall.trace_id == trace_id).order_by(LlmCall.created_at)
            )
        )


def test_classify_and_extract_ok(
    owner_engine: Engine, app_factory: sessionmaker[Session], tenant_a: Tenant
) -> None:
    t = ScriptedTransport({**CLASIFICA, "CuentaCobro": [cuenta_cobro_json()]})
    out, tracked = _run(t, tenant_a, app_factory, trace_id="trace-ok")

    assert out.status == "extracted", out.error
    assert out.method == "pdf_text"
    assert out.doc_type == "cuenta_cobro"
    assert out.model == FAKE_MODEL
    assert out.prompt_version == "extraccion-1"
    values = {f.name: f.value for f in out.fields}
    assert values["valor"] == "1500000.00"
    assert values["nit_pagador"] == "800197268"
    assert values["fecha"] == "2026-10-20"
    assert not out.doubtful_fields

    # Temperatura 0 fija en cada petición; el texto del PDF llega al modelo.
    assert t.tools_called() == ["Clasificacion", "CuentaCobro"]
    assert all(r["temperature"] == EXTRACTION_TEMPERATURE == 0 for r in t.requests)
    assert "CUENTA DE COBRO No. 015" in t.requests[0]["messages"][-1]["content"]

    # Una fila por llamada, con costo, tokens, latencia, trace_id y document_id.
    calls = _calls(owner_engine, "trace-ok")
    assert [c.purpose for c in calls] == ["clasificacion", "extraccion"]
    assert [c.prompt_version for c in calls] == ["clasificacion-1", "extraccion-1"]
    for c in calls:
        assert c.organization_id == tenant_a.org_id
        assert c.document_id == tenant_a.document_id
        assert (c.provider, c.model, c.status) == ("openai", FAKE_MODEL, "ok")
        assert (c.input_tokens, c.output_tokens) == (1000, 200)
        assert c.cost_usd == COST_PER_CALL
        assert c.latency_ms >= 0
    assert tracked.spent_usd == 2 * COST_PER_CALL
    assert out.raw_output["costo_usd"] == str(2 * COST_PER_CALL)


def test_retry_fixes_invalid_dv(
    owner_engine: Engine, app_factory: sessionmaker[Session], tenant_a: Tenant
) -> None:
    # Intento 1: DV del pagador mal (validador de dominio). Intento 2: corregido.
    t = ScriptedTransport(
        {**CLASIFICA, "CuentaCobro": [cuenta_cobro_json(dv_pagador=7), cuenta_cobro_json()]}
    )
    out, _ = _run(t, tenant_a, app_factory, trace_id="trace-retry")
    assert out.status == "extracted", out.error
    assert out.raw_output["intentos"] == 2
    # El reintento le dice al modelo qué falló.
    assert "dv_nit" in t.requests[-1]["messages"][-1]["content"]
    assert len(_calls(owner_engine, "trace-retry")) == 3


def test_invalid_fields_end_doubtful_after_retries(
    owner_engine: Engine, app_factory: sessionmaker[Session], tenant_a: Tenant
) -> None:
    # Siempre: NIT del cobrador con letras (esquema) y DV del pagador mal (validador).
    bad = cuenta_cobro_json(nit_cobrador="CC-ABC", dv_pagador=7)
    t = ScriptedTransport({**CLASIFICA, "CuentaCobro": [bad]})
    out, _ = _run(t, tenant_a, app_factory, retries=2, trace_id="trace-doubt")

    assert out.status == "needs_review"
    assert out.raw_output["intentos"] == 3  # 1 + 2 reintentos, acotado
    flags = {f.name: f.is_doubtful for f in out.fields}
    values = {f.name: f.value for f in out.fields}
    assert flags["nit_cobrador"] is True
    assert values["nit_cobrador"] is None  # no se inventa: se anula y se marca
    assert out.raw_output["invalidos"] == {"nit_cobrador": "CC-ABC"}
    assert flags["nit_pagador"] is True
    assert flags["dv_pagador"] is True
    assert values["dv_pagador"] == 7  # el valor leído se conserva para la revisión
    assert flags["valor"] is False
    assert flags["concepto"] is False
    assert "Campos dudosos" in (out.error or "")
    calls = _calls(owner_engine, "trace-doubt")
    assert len(calls) == 4
    assert calls[1].error is not None
    assert "esquema" in calls[1].error


def test_cost_cap_stops_and_flags_review(
    owner_engine: Engine, app_factory: sessionmaker[Session], tenant_a: Tenant
) -> None:
    # Tope 0.003: clasificar (0.002) + extraer (0.004 > tope) → no hay reintento.
    bad = cuenta_cobro_json(dv_pagador=7)
    t = ScriptedTransport({**CLASIFICA, "CuentaCobro": [bad]})
    out, tracked = _run(t, tenant_a, app_factory, cap="0.003", retries=2, trace_id="trace-cap")
    assert tracked.cap_exceeded
    assert out.status == "needs_review"
    assert out.raw_output["tope_costo_superado"] is True
    assert "Tope de costo" in (out.error or "")
    assert len(_calls(owner_engine, "trace-cap")) == 2
    assert len(t.requests) == 2


def test_cost_cap_reached_before_extraction(
    owner_engine: Engine, app_factory: sessionmaker[Session], tenant_a: Tenant
) -> None:
    # Tope 0.002: la clasificación lo agota; la extracción no se llega a pedir.
    t = ScriptedTransport({**CLASIFICA, "CuentaCobro": [cuenta_cobro_json()]})
    out, _ = _run(t, tenant_a, app_factory, cap="0.002", trace_id="trace-cap2")
    assert out.status == "needs_review"
    assert out.doc_type == "cuenta_cobro"
    assert out.fields == []
    assert t.tools_called() == ["Clasificacion"]
    assert len(_calls(owner_engine, "trace-cap2")) == 1


def test_tracked_llm_refuses_when_cap_reached(
    app_factory: sessionmaker[Session], tenant_a: Tenant
) -> None:
    tracked = TrackedLLM(
        scripted_llm(ScriptedTransport(CLASIFICA)),
        FAKE_PRICES,
        organization_id=tenant_a.org_id,
        document_id=tenant_a.document_id,
        trace_id="trace-x",
        max_cost_usd=Decimal("0.001"),
        factory=app_factory,
    )
    tracked.spent_usd = Decimal("0.001")
    with pytest.raises(CostCapExceededError):
        tracked.structured(
            purpose="clasificacion",
            prompt_version="v",
            model=FAKE_MODEL,
            messages=[],
            response_model=Clasificacion,
        )


def test_unknown_price_fails_closed(
    owner_engine: Engine, app_factory: sessionmaker[Session], tenant_a: Tenant
) -> None:
    t = ScriptedTransport(CLASIFICA)
    tracked = TrackedLLM(
        scripted_llm(t),
        PriceTable(),  # sin precios
        organization_id=tenant_a.org_id,
        document_id=tenant_a.document_id,
        trace_id="trace-noprice",
        max_cost_usd=Decimal("1"),
        factory=app_factory,
    )
    with pytest.raises(LLMNotConfiguredError, match="Sin precio"):
        classify("texto", tracked, model=FAKE_MODEL, max_retries=0)
    assert t.requests == []  # no se llamó al modelo
    assert _calls(owner_engine, "trace-noprice") == []


def test_provider_error_is_recorded(
    owner_engine: Engine, app_factory: sessionmaker[Session], tenant_a: Tenant
) -> None:
    t = ScriptedTransport(CLASIFICA, fail_with=500)
    out, _ = _run(t, tenant_a, app_factory, trace_id="trace-500")
    assert out.status == "failed"
    assert "proveedor LLM" in (out.error or "")
    calls = _calls(owner_engine, "trace-500")
    assert len(calls) == 1
    assert calls[0].status == "error"
    assert calls[0].cost_usd == Decimal(0)


def test_default_price_table_loads() -> None:
    table = PriceTable.load()
    assert table.version == 1
