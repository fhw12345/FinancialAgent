"""Deterministic Direct, ReAct, and Deep streams for UAW-009."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from src.agent.flow_router import FlowRoutingDecision
from src.agent.portfolio import flows as portfolio_flows
from src.api.dependencies.chat_deps import (
    get_chat_agent,
    get_deep_agent,
    get_flow_router,
    get_react_agent,
)
from src.main import app
from src.models.symbol_resolution import SymbolCandidate, SymbolResolution
from src.services.cache_warming_service import CacheWarmingService

execution_count = 0


class EventRouter:
    async def select(self, *, message: str, **kwargs: Any) -> FlowRoutingDecision:
        if "REACT" in message:
            flow = "v3"
        elif "DEEP" in message:
            flow = "v4-deep"
        else:
            flow = "v2"
        return FlowRoutingDecision(
            flow=flow,
            source="rule",
            reason_code=f"uaw009_{flow}",
        )


class DirectAgent:
    async def stream_chat(self, **kwargs: Any):
        global execution_count
        execution_count += 1
        yield "DIRECT_ENVELOPE_OK"

    def get_last_token_usage(self):
        return SimpleNamespace(total_tokens=2, input_tokens=1, output_tokens=1)


class ReactAgent:
    async def ainvoke(self, **kwargs: Any) -> dict[str, Any]:
        callback = kwargs["additional_callbacks"][0]
        tool_run_id = uuid4()
        await callback.on_tool_start(
            {"name": "get_company_overview"},
            "",
            run_id=tool_run_id,
            inputs={"symbol": "AAPL"},
        )
        await callback.on_tool_end(
            {"symbol": "AAPL", "status": "ok"},
            run_id=tool_run_id,
        )
        return {
            "final_answer": "REACT_ENVELOPE_OK",
            "tool_executions": 1,
            "trace_id": "uaw009_react",
        }


class DeepAgent:
    async def resolve_symbol(self, **kwargs: Any) -> SymbolResolution:
        candidate = SymbolCandidate(
            symbol="AAPL",
            name="Apple",
            confidence=1.0,
        )
        return SymbolResolution(
            status="resolved",
            source="explicit_ticker",
            reason_code="resolved_explicit_ticker",
            symbol="AAPL",
            company_name="Apple",
            confidence=1.0,
            candidates=[candidate],
        )

    async def ainvoke(self, **kwargs: Any) -> dict[str, Any]:
        on_event = kwargs["on_event"]
        on_event(
            {
                "type": "deep_start",
                "seq": 1,
                "timestamp": "2026-07-21T02:00:00Z",
                "symbol": "AAPL",
                "subagent_names": ["technical_analyst"],
                "enable_debate": False,
            }
        )
        on_event(
            {
                "type": "deep_verdict",
                "seq": 2,
                "timestamp": "2026-07-21T02:00:01Z",
                "verdict_text": "DEEP_ENVELOPE_OK",
                "risk_level": "MODERATE",
                "tool_count": 0,
                "total_duration_ms": 10,
            }
        )
        return {
            "final_answer": "DEEP_ENVELOPE_OK",
            "tool_executions": 0,
            "trace_id": "uaw009_deep",
            "research_context": {},
            "prompt_versions": {
                "deep-debater": "deep-debater@2",
                "deep-verdict": "deep-verdict@1",
            },
        }


async def skip_cache_warming(
    self: CacheWarmingService,
    symbols: list[str] | None = None,
) -> dict[str, object]:
    return {"status": "skipped", "reason": "uaw009_e2e"}


app.dependency_overrides[get_flow_router] = lambda: EventRouter()
app.dependency_overrides[get_chat_agent] = lambda: DirectAgent()
app.dependency_overrides[get_react_agent] = lambda: ReactAgent()
app.dependency_overrides[get_deep_agent] = lambda: DeepAgent()
CacheWarmingService.warm_startup_cache = skip_cache_warming


@app.get("/api/test/idempotency-count")
async def idempotency_count() -> dict[str, int]:
    return {"execution_count": execution_count}


async def governed_holdings_flow(app: Any, settings: Any) -> dict[str, Any]:
    return {
        "message": "PROMPT_GOVERNANCE_PORTFOLIO_OK",
        "result_count": 1,
    }


portfolio_flows.run_analyze_holdings = governed_holdings_flow
