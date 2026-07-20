"""Deterministic Direct stream app for UAW-007 durable run E2E."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from src.agent.flow_router import FlowRoutingDecision
from src.api.dependencies.chat_deps import get_chat_agent, get_flow_router
from src.main import app
from src.services.cache_warming_service import CacheWarmingService


class DirectRunRouter:
    async def select(self, **kwargs: Any) -> FlowRoutingDecision:
        return FlowRoutingDecision(
            flow="v2",
            source="rule",
            reason_code="uaw007_shared_run",
        )


class SlowTokenAgent:
    async def stream_chat(self, **kwargs: Any):
        yield "RUN_STARTED"
        await asyncio.sleep(3)
        yield " RUN_COMPLETED"

    def get_last_token_usage(self):
        return SimpleNamespace(
            total_tokens=3,
            input_tokens=2,
            output_tokens=1,
        )


async def skip_startup_cache_warming(
    self: CacheWarmingService,
    symbols: list[str] | None = None,
) -> dict[str, object]:
    return {"status": "skipped", "reason": "uaw007_e2e"}


app.dependency_overrides[get_flow_router] = lambda: DirectRunRouter()
app.dependency_overrides[get_chat_agent] = lambda: SlowTokenAgent()
CacheWarmingService.warm_startup_cache = skip_startup_cache_warming
