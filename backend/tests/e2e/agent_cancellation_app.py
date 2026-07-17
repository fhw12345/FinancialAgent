"""FastAPI app with a deterministic cancellable ReAct agent for UAW-005."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Any

from src.agent.flow_router import FlowRoutingDecision
from src.api.dependencies.chat_deps import get_flow_router, get_react_agent
from src.main import app
from src.services.cache_warming_service import CacheWarmingService


@dataclass
class CancellationProbe:
    agent_started: bool = False
    agent_cancelled: bool = False
    child_cancelled: bool = False
    agent_completed: bool = False
    late_event_emitted: bool = False


probe = CancellationProbe()


class DeterministicV3Router:
    """Route every test request through the cancellable ReAct handler."""

    async def select(self, **kwargs: Any) -> FlowRoutingDecision:
        return FlowRoutingDecision(
            flow="v3",
            source="rule",
            reason_code="uaw005_cancellation_e2e",
        )


class SlowCancellableAgent:
    """One awaited child task proves cancellation propagation."""

    async def ainvoke(self, **kwargs: Any) -> dict[str, Any]:
        global probe
        probe = CancellationProbe(agent_started=True)
        for callback in kwargs.get("additional_callbacks") or []:
            callback.event_queue.put_nowait(
                {
                    "type": "tool_start",
                    "tool_name": "uaw005_cancellation_probe",
                    "display_name": "Cancellation Probe",
                    "icon": "⏳",
                    "symbol": "AAPL",
                    "run_id": "uaw005_probe",
                    "inputs": {},
                }
            )

        async def child_work() -> None:
            try:
                await asyncio.sleep(300)
                probe.late_event_emitted = True
            except asyncio.CancelledError:
                probe.child_cancelled = True
                raise

        child = asyncio.create_task(child_work())
        try:
            await child
            probe.agent_completed = True
            return {
                "final_answer": "This response should never complete.",
                "tool_executions": 0,
                "trace_id": "uaw005_unexpected_completion",
            }
        except asyncio.CancelledError:
            probe.agent_cancelled = True
            if not child.done():
                child.cancel()
            try:
                await child
            except asyncio.CancelledError:
                pass
            raise


async def skip_startup_cache_warming(
    self: CacheWarmingService,
    symbols: list[str] | None = None,
) -> dict[str, object]:
    return {"status": "skipped", "reason": "uaw005_e2e"}


@app.get("/api/e2e/cancellation-status")
async def cancellation_status() -> dict[str, Any]:
    persisted = False
    mongodb = getattr(app.state, "mongodb", None)
    if mongodb is not None:
        message = await mongodb.get_collection("messages").find_one(
            {"metadata.run_status": "cancelled"}
        )
        persisted = message is not None
    return {**asdict(probe), "cancellation_persisted": persisted}


app.dependency_overrides[get_flow_router] = lambda: DeterministicV3Router()
app.dependency_overrides[get_react_agent] = lambda: SlowCancellableAgent()
CacheWarmingService.warm_startup_cache = skip_startup_cache_warming
