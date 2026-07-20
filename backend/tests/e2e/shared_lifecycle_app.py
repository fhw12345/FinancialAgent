"""Deterministic Direct and Deep app for UAW-008 browser coverage."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from src.agent.flow_router import FlowRoutingDecision
from src.api.dependencies.chat_deps import (
    get_chat_agent,
    get_deep_agent,
    get_flow_router,
)
from src.main import app
from src.models.symbol_resolution import SymbolCandidate, SymbolResolution
from src.services.cache_warming_service import CacheWarmingService


class LifecycleRouter:
    async def select(self, *, message: str, **kwargs: Any) -> FlowRoutingDecision:
        if "Alpha" in message:
            return FlowRoutingDecision(
                flow="v4-deep",
                source="rule",
                reason_code="uaw008_deep_clarification",
            )
        return FlowRoutingDecision(
            flow="v2",
            source="rule",
            reason_code="uaw008_direct_completion",
        )


class DirectLifecycleAgent:
    async def stream_chat(self, **kwargs: Any):
        yield "LIFECYCLE_DIRECT_COMPLETE"

    def get_last_token_usage(self):
        return SimpleNamespace(
            total_tokens=4,
            input_tokens=3,
            output_tokens=1,
        )


class ClarifyingDeepAdapter:
    async def resolve_symbol(self, **kwargs: Any) -> SymbolResolution:
        return SymbolResolution(
            status="ambiguous",
            source="llm_assisted",
            reason_code="ambiguous_symbol",
            candidates=[
                SymbolCandidate(
                    symbol="AAA",
                    name="Alpha A",
                    exchange="NYSE",
                    confidence=0.9,
                ),
                SymbolCandidate(
                    symbol="AAB",
                    name="Alpha B",
                    exchange="NASDAQ",
                    confidence=0.85,
                ),
            ],
        )

    async def ainvoke(self, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("Deep engine must not run before clarification")


async def skip_startup_cache_warming(
    self: CacheWarmingService,
    symbols: list[str] | None = None,
) -> dict[str, object]:
    return {"status": "skipped", "reason": "uaw008_e2e"}


app.dependency_overrides[get_flow_router] = lambda: LifecycleRouter()
app.dependency_overrides[get_chat_agent] = lambda: DirectLifecycleAgent()
app.dependency_overrides[get_deep_agent] = lambda: ClarifyingDeepAdapter()
CacheWarmingService.warm_startup_cache = skip_startup_cache_warming
