"""Real review UI/API/graph/storage. Only outer transports, clock and explicit storage faults."""

import asyncio
import json
from datetime import timedelta

import httpx
import pandas as pd
import yfinance as yf
from motor.motor_asyncio import AsyncIOMotorCollection

from src.services.decision_policy import (
    builder,
    policies,
    review_gate,
    review_projection,
    review_service,
)
from tests.e2e import decision_policy_app as decision
from tests.e2e import evidence_app as evidence
from tests.e2e import strategy_app as strategy
from tests.copilot_fixtures import sse

app = strategy.app
fault = "none"
reached = asyncio.Event()
release = asyncio.Event()
original_write = AsyncIOMotorCollection.find_one_and_update
transport_calls = []
storage_clock_offset = timedelta()


class ReviewTicker(strategy.StrategyTicker):
    @property
    def income_stmt(self):
        frame = super().income_stmt
        frame[pd.Timestamp("2024-12-31")] = {
            "Diluted EPS": 4.0,
            "Diluted Average Shares": 10000000.0,
            "Interest Expense": 10000000.0,
            "Total Revenue": 180000000.0,
            "Net Income": 40000000.0,
        }
        return frame


yf.Ticker = ReviewTicker
for module in (policies, review_gate, review_projection, review_service):
    module.datetime = evidence.Clock
builder.utcnow = lambda: evidence.Clock.now()


async def transport(request):
    body = json.loads(request.content)
    transport_calls.append(body.get("model"))
    names = [tool.get("name") for tool in body.get("tools", [])]
    if "GateVerdict" in names:
        decision.model_calls.append(body["model"])
        return sse(
            [
                {
                    "type": "function_call",
                    "name": "GateVerdict",
                    "call_id": "consistency",
                    "arguments": json.dumps({"passed": True, "violations": []}),
                }
            ]
        )
    if "get_stock_quote" in names and not any(
        item.get("type") == "function_call_output" for item in body.get("input", [])
    ):
        reviews = []
        for text in evidence.strings(body.get("input", [])):
            for line in text.splitlines():
                try:
                    value = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if (
                    isinstance(value, dict)
                    and "review_id" in value
                    and "symbol" in value
                ):
                    reviews.append(value)
        if reviews:
            decision.model_calls.append(body["model"])
            return sse(
                [
                    {
                        "type": "function_call",
                        "name": "get_stock_quote",
                        "call_id": "quote",
                        "arguments": json.dumps({"symbol": reviews[0]["symbol"]}),
                    }
                ]
            )
    return await strategy.transport(request)


strategy.service.transport = httpx.MockTransport(transport)


async def guarded_write(self, *args, **kwargs):
    update = args[1] if len(args) > 1 else kwargs.get("update", {})
    if fault == "prepare_fail" and self.name == "review_batches":
        raise RuntimeError("Recorded review preparation storage failure")
    if (
        fault == "approve_pause"
        and self.name == "review_control"
        and (update.get("$set", {}).get("current") or {}).get("state") == "approved"
    ):
        reached.set()
        await release.wait()
    if self.name == "review_control" and args and "$expr" in args[0]:
        # Recorded clock at the outer Mongo transport ONLY. Mongo still evaluates
        # the actual deadline expression and full revision/generation/ticket CAS.
        query = dict(args[0])
        comparison = query["$expr"]["$lt"]
        assert comparison[0] == "$$NOW"
        query["$expr"] = {
            "$lt": [evidence.Clock.now() + storage_clock_offset, comparison[1]]
        }
        args = (query, *args[1:])
    return await original_write(self, *args, **kwargs)


AsyncIOMotorCollection.find_one_and_update = guarded_write


@app.post("/api/test/review/reset/{scenario}")
async def reset(scenario: str):
    global fault, reached, release, storage_clock_offset
    assert scenario in ("normal", "missing")
    fault = "none"
    storage_clock_offset = timedelta()
    reached = asyncio.Event()
    release = asyncio.Event()
    await strategy.reset_strategy(scenario)
    transport_calls.clear()
    return {"reset": True}


@app.get("/api/test/review/audit")
async def audit():
    db = app.state.mongodb
    holdings = [
        {key: row.get(key) for key in ("symbol", "quantity", "cost_basis")}
        async for row in db.get_collection("holdings").find({}).sort("symbol", 1)
    ]
    settings = await db.get_collection("user_settings").find_one({}) or {}
    return {
        "holdings": holdings,
        "cash": settings.get("cash_balance"),
        "model_requests": len(transport_calls),
        "counts": {
            name: await db.get_collection(name).count_documents({})
            for name in (
                "user_transactions",
                "transactions",
                "portfolio_orders",
                "paper_fills",
            )
        },
    }


@app.post("/api/test/review/fault/{name}")
async def set_fault(name: str):
    global fault
    assert name in ("none", "prepare_fail", "approve_pause")
    fault = name
    return {"fault": fault}


@app.get("/api/test/review/reached")
async def paused():
    return {"paused": reached.is_set()}


@app.post("/api/test/review/expire-storage-clock")
async def expire_storage_clock():
    global storage_clock_offset
    storage_clock_offset = timedelta(hours=2)
    return {"clock_advanced": True}


@app.post("/api/test/review/release")
async def release_approval():
    release.set()
    return {"released": True}
