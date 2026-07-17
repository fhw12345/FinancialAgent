"""Deterministic Direct/ReAct streaming semantics app for UAW-006."""

from __future__ import annotations

import asyncio
from typing import Any

from src.agent.flow_router import FlowRoutingDecision
from src.api.dependencies.chat_deps import (
    get_chat_agent,
    get_flow_router,
    get_react_agent,
)
from src.main import app
from src.services.cache_warming_service import CacheWarmingService


class SemanticsRouter:
    async def select(
        self,
        *,
        message: str,
        **kwargs: Any,
    ) -> FlowRoutingDecision:
        if "concept" in message.lower():
            return FlowRoutingDecision(
                flow="v2",
                source="rule",
                reason_code="uaw006_direct_stream",
            )
        return FlowRoutingDecision(
            flow="v3",
            source="rule",
            reason_code="uaw006_buffered_agent",
        )


class TokenStreamingAgent:
    async def stream_chat(self, **kwargs: Any):
        yield "FIRST_TOKEN"
        await asyncio.sleep(3)
        yield " SECOND_TOKEN"

    def get_last_token_usage(self):
        return None


class BufferedReactAgent:
    async def ainvoke(self, **kwargs: Any) -> dict[str, Any]:
        for callback in kwargs.get("additional_callbacks") or []:
            callback.event_queue.put_nowait(
                {
                    "type": "tool_start",
                    "tool_name": "uaw006_buffered_probe",
                    "display_name": "Buffered Progress",
                    "icon": "📦",
                    "symbol": "AAPL",
                    "run_id": "uaw006_probe",
                    "inputs": {},
                }
            )
        await asyncio.sleep(3)
        return {
            "final_answer": "BUFFERED_RESPONSE_COMPLETE",
            "tool_executions": 1,
            "trace_id": "uaw006_buffered",
        }


async def skip_startup_cache_warming(
    self: CacheWarmingService,
    symbols: list[str] | None = None,
) -> dict[str, object]:
    return {"status": "skipped", "reason": "uaw006_e2e"}


app.dependency_overrides[get_flow_router] = lambda: SemanticsRouter()
app.dependency_overrides[get_chat_agent] = lambda: TokenStreamingAgent()
app.dependency_overrides[get_react_agent] = lambda: BufferedReactAgent()
CacheWarmingService.warm_startup_cache = skip_startup_cache_warming
