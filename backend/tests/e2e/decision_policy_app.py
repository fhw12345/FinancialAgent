"""Real Stage-A app/flows/LLM graph/storage; recorded model and market transports."""

import asyncio
import copy
import json
import time
from datetime import UTC, datetime

import httpx
import pandas as pd
import yfinance as yf
from types import SimpleNamespace
from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import SecretStr

from src.core.utils.date_utils import utcnow
from src.database.repositories.agent_run_repository import AgentRunRepository
from src.database.repositories.decision_assessment_repository import (
    DecisionAssessmentRepository,
)
from src.models.portfolio import PortfolioOrder
from src.services.agent_run_service import AgentRunService
from src.services.alphavantage_market_data import AlphaVantageMarketDataService
from src.services.data_manager import CacheKeys
from src.services.market_data import yfinance_movers
from tests.e2e.copilot_app import app, service
from tests.copilot_fixtures import sse, text_output
from src.services.copilot.catalog import CopilotModel

# Keep the normal API/CORS/cache path; the inherited widget middleware short-circuits it.
app.user_middleware = [
    middleware
    for middleware in app.user_middleware
    if getattr(middleware.kwargs.get("dispatch"), "__name__", "") != "no_market_widgets"
]


async def recorded_movers():
    return {
        "top_gainers": [],
        "top_losers": [],
        "most_actively_traded": [],
        "source": "recorded",
    }


yfinance_movers.get_market_movers = recorded_movers
mode = "good"
model_calls = []
release = asyncio.Event()
saved_agent = None
original_write = AsyncIOMotorCollection.find_one_and_update
original_assess = DecisionAssessmentRepository.assess_and_persist
captured_inputs = None


async def observed_assess(self, **inputs):
    global captured_inputs
    captured_inputs = copy.deepcopy(inputs)
    return await original_assess(self, **inputs)


DecisionAssessmentRepository.assess_and_persist = observed_assess


async def model_transport(request):
    if request.url.path != "/responses":
        raise AssertionError("Unexpected provider request")
    body = json.loads(request.content)
    model_calls.append(body["model"])
    tools = body.get("tools", [])
    names = [t["name"] for t in tools]
    if "GateVerdict" in names:
        if mode == "check_unavailable":
            return httpx.Response(503)
        return sse(
            [
                {
                    "type": "function_call",
                    "call_id": "gate",
                    "name": "GateVerdict",
                    "arguments": json.dumps(
                        {
                            "passed": False,
                            "violations": [
                                {
                                    "field": "Cash flow",
                                    "quote": "Unsupported cashflow claim",
                                }
                            ],
                        }
                    ),
                }
            ]
        )
    if "GovernedPortfolioDecisionList" in names:
        return sse(
            [
                {
                    "type": "function_call",
                    "call_id": "decision",
                    "name": "GovernedPortfolioDecisionList",
                    "arguments": json.dumps(
                        {
                            "decisions": [
                                {
                                    "symbol": "MSFT" if mode == "rogue" else "AAPL",
                                    "decision": "BUY",
                                    "position_size_percent": 10,
                                    "entry_price": 100,
                                    "stop_loss": 90,
                                    "take_profit": 120,
                                    "confidence": 7,
                                    "reasoning_summary": "Recorded model draft, not approved.",
                                }
                            ],
                            "portfolio_assessment": "Recorded assessment draft",
                        }
                    ),
                }
            ]
        )
    if any(
        item.get("type") == "function_call_output" for item in body.get("input", [])
    ):
        if mode == "paused":
            await release.wait()
        text = "Recorded research based on the quote tool."
        if mode in ("missing", "check_unavailable"):
            text = "⚠️ **Cash flow unavailable for AAPL.** Cash flow is healthy."
        return sse(text_output(text))
    if "get_stock_quote" in names:
        return sse(
            [
                {
                    "type": "function_call",
                    "call_id": "quote",
                    "name": "get_stock_quote",
                    "arguments": '{"symbol":"AAPL"}',
                }
            ]
        )
    return sse(text_output("Recorded text"))


class RecordedTicker:
    def __init__(self, symbol):
        self.symbol = symbol

    @property
    def fast_info(self):
        if mode == "missing":
            raise RuntimeError("Recorded quote provider unavailable")
        return SimpleNamespace(
            last_price=100,
            previous_close=99,
            last_volume=1000000,
            open=99,
            day_high=101,
            day_low=98,
        )

    @property
    def info(self):
        return {
            "sector": "Technology",
            "beta": 1.0,
            "symbol": self.symbol,
            "regularMarketPrice": 100,
            "currency": "USD",
            "quoteType": "EQUITY",
        }

    def history(self, **kwargs):
        if kwargs.get("auto_adjust") is False:
            if mode == "missing":
                raise RuntimeError("Recorded closing quote unavailable")
            from src.services.portfolio_risk.calendar import sessions
            from datetime import date, timedelta

            end = date.fromisoformat(kwargs["end"]) - timedelta(days=1)
            dates = sessions(end, 61)
            adjusted = [100.0]
            for change in [-0.02, 0.02] * 30:
                adjusted.append(adjusted[-1] * (1 + change))
            return pd.DataFrame(
                {"Close": [100.0] * 61, "Adj Close": adjusted},
                index=pd.to_datetime(dates),
            )
        return pd.DataFrame(
            {"Close": [99, 100] * 31, "Volume": [1000000] * 62},
            index=pd.date_range(end=datetime.now(UTC), periods=62, freq="D"),
        )


async def unavailable_av_quote(self, symbol):
    raise RuntimeError("Recorded fallback quote unavailable")


async def market_status(self, *args, **kwargs):
    return {
        "current_status": "open",
        "local_time": "recorded",
        "utc_time": "recorded",
        "notes": "",
    }


async def guarded_write(self, *args, **kwargs):
    if mode == "storage_fail" and self.name == "decision_assessments":
        raise RuntimeError("Recorded assessment write failure")
    return await original_write(self, *args, **kwargs)


service.transport = httpx.MockTransport(model_transport)
yf.Ticker = RecordedTicker
AlphaVantageMarketDataService.get_quote = unavailable_av_quote
AlphaVantageMarketDataService.get_market_status = market_status
AsyncIOMotorCollection.find_one_and_update = guarded_write


async def recorded_search(self, query, limit=10):
    return [
        {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "exchange": "NASDAQ",
            "type": "Equity",
            "match_type": "exact_symbol",
            "confidence": 1.0,
        }
    ]


AlphaVantageMarketDataService.search_symbols = recorded_search


@app.post("/api/test/idq/reset/{scenario}")
async def reset(scenario: str):
    global mode, release, saved_agent
    assert scenario in (
        "good",
        "missing",
        "check_unavailable",
        "no_agent",
        "storage_fail",
        "paused",
        "rogue",
    )
    mode = scenario
    await app.state.redis.delete(CacheKeys.quote("AAPL"))
    await app.state.redis.delete(CacheKeys.quote_ext("AAPL"))
    release = asyncio.Event()
    model_calls.clear()
    if saved_agent is None:
        saved_agent = app.state.portfolio_agent
    app.state.portfolio_agent = None if scenario == "no_agent" else saved_agent
    mongo = app.state.mongodb
    for name in [
        "holdings",
        "portfolio_orders",
        "decision_assessments",
        "risk_policy",
        "portfolio_risk_captures",
        "agent_runs",
        "user_transactions",
        "chats",
        "messages",
    ]:
        await mongo.get_collection(name).delete_many({})
    await mongo.get_collection("user_settings").update_one(
        {},
        {
            "$set": {
                "cash_balance": 10000,
                "risk_tolerance": "moderate",
                "max_position_pct": 10,
            }
        },
        upsert=True,
    )
    await mongo.get_collection("holdings").insert_one(
        {
            "holding_id": "holding_fixture",
            "symbol": "AAPL",
            "quantity": 10,
            "avg_price": 90,
            "current_price": 100,
            "market_value": 1000,
            "cost_basis": 900,
            "created_at": utcnow(),
            "updated_at": utcnow(),
        }
    )
    legacy = PortfolioOrder(
        order_id="legacy_order",
        chat_id="legacy_chat",
        analysis_id="legacy_analysis",
        symbol="AAPL",
        order_type="limit",
        side="buy",
        quantity=2,
        status="suggested",
        created_at=utcnow(),
        decision_price=100,
        metadata={
            "reasoning": "Old unverified BUY draft",
            "full_research": "Historical research remains readable.",
        },
    )
    await mongo.get_collection("portfolio_orders").insert_one(legacy.model_dump())
    state = service.store.read()
    state.github_token = SecretStr("fake-gh")
    state.access_token = SecretStr("fake-cp")
    state.expires_at = time.time() + 3600
    state.selected_model = "gpt-6-astra"
    state.role_models = {}
    state.models = [CopilotModel(id="gpt-6-astra", name="Recorded")]
    state.catalog_at = time.time()
    service.store.save(state)
    return {"reset": True}


@app.post("/api/test/idq/cancel/{run_id}")
async def cancel(run_id: str):
    runs = AgentRunService(
        AgentRunRepository(app.state.mongodb.get_collection("agent_runs"))
    )
    await runs.cancel(run_id, cancel_reason="recorded_user_stop")
    release.set()
    return {"cancelled": True}


@app.post("/api/test/idq/replay/{changed}")
async def replay(changed: bool):
    assert captured_inputs is not None
    inputs = copy.deepcopy(captured_inputs)
    if changed:
        inputs["research"] = {"AAPL": "Different research"}
    repository = DecisionAssessmentRepository(
        app.state.mongodb.get_collection("decision_assessments")
    )
    assessment = await original_assess(repository, **inputs)
    return {
        "assessment_id": assessment.assessment_id,
        "actionable": assessment.actionable,
    }


@app.get("/api/test/idq/evidence")
async def evidence():
    mongo = app.state.mongodb
    return {
        "model_calls": len(model_calls),
        "orders": await mongo.get_collection("portfolio_orders").count_documents({}),
        "transactions": await mongo.get_collection("user_transactions").count_documents(
            {}
        ),
        "assessments": await mongo.get_collection(
            "decision_assessments"
        ).count_documents({}),
    }
