"""Isolated live/replay portfolio acceptance app; NEVER import fake-login fixtures here."""

import asyncio
import json
import os
from pathlib import Path
from contextlib import asynccontextmanager

import httpx
import yfinance as yf
from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import SecretStr

from src.core.config import get_settings
from src.api.copilot import local_action, no_store
from src.services.copilot.service import get_copilot_service
from src.services.copilot.catalog import CopilotModel
from src.services.cache_warming_service import CacheWarmingService
from src.services.finnhub.service import FinnhubService
from src.services.data_manager.types import QuoteData
from src.services.market_data import yfinance_movers
from tests.model_portfolios.inputs import SyntheticTicker, seed
from tests.model_portfolios.budget import (
    Budget,
    CURRENT_CASE,
    GuardedTransport,
    BudgetStopped,
)
from tests.model_portfolios.cases import case, manifest
from tests.model_portfolios.report import ledger_hashes, observe
from tests.copilot_fixtures import sse

settings = get_settings()
if settings.environment != "test" or not settings.mongodb_url.rsplit("/", 1)[-1].split(
    "?"
)[0].startswith("model_portfolios_"):
    raise RuntimeError(
        "Acceptance app requires a dedicated model_portfolios_ test database"
    )
MODE = os.getenv("MODEL_PORTFOLIO_MODE", "replay")
from uuid import uuid4

RUN_ID = os.getenv("MODEL_PORTFOLIO_RUN_ID", "replay_" + uuid4().hex[:16])
if MODE not in ("replay", "live"):
    raise RuntimeError("Unknown acceptance mode")
if MODE == "live" and (
    os.getenv("MODEL_PORTFOLIO_AUTHORIZATION") != "max6-astra-4096-600@2026-10-09"
    or RUN_ID != "idq009a-20261009-live-001"
):
    raise RuntimeError(
        "Live mode requires the specific authorized run identity and ceiling"
    )
if MODE == "replay" and not settings.copilot_state_dir.startswith("/tmp/"):
    raise RuntimeError("Replay mode cannot mount or replace private live credentials")

from src.main import app

native = get_copilot_service()
original_lifespan = app.router.lifespan_context
active = {}
pinned = None


def authorize():
    current = native.store.read()
    if (
        pinned is None
        or (
            current.generation,
            current.routing_revision,
            current.role_models.get("portfolio_decisions", current.selected_model),
        )
        != pinned
    ):
        raise BudgetStopped("Account/routing changed; no fallback model permitted")


def recorded(request):
    if request.url.path == "/responses":
        body = json.loads(request.content)
        inputs = "\n".join(json.dumps(i, ensure_ascii=False) for i in body["input"])
        # Captured native prompt is a JSON string in the Responses input. Find
        # only the displayed evidence IDs; no browser/server gate result is mocked.
        assert (
            "Synthetic sealed research" in inputs
        ), "The actual decision prompt must bind the synthetic source"

        def strings(value):
            if isinstance(value, str):
                yield value
            elif isinstance(value, list):
                for item in value:
                    yield from strings(item)
            elif isinstance(value, dict):
                for item in value.values():
                    yield from strings(item)

        receipts = []
        for text in strings(body["input"]):
            for line in text.splitlines():
                try:
                    value = json.loads(line)
                except ValueError:
                    continue
                if (
                    isinstance(value, list)
                    and value
                    and isinstance(value[0], dict)
                    and "evidence_ids" in value[0]
                ):
                    receipts = value
        rows = [
            {
                "symbol": s,
                "action": "HOLD",
                "target_weight": None,
                "rationale": "Recorded conservative recommendation",
                "evidence_ids": [],
                "key_risks": ["Synthetic inputs are uncertain"],
                "review_triggers": ["Review financial changes"],
            }
            for s in ("AAPL", "MSFT")
        ]
        if CURRENT_CASE.get() == "cash-rich":
            own = next(r for r in receipts if r["symbol"] == "AAPL")
            rows[0].update(
                action="ADD",
                target_weight=0.2,
                evidence_ids=own["evidence_ids"][:1],
                rationale="Recorded compliant ADD for positive review/approval path",
            )
        return sse(
            [
                {
                    "type": "function_call",
                    "name": "ModelDecisionSet",
                    "call_id": "acceptance",
                    "arguments": json.dumps(
                        {
                            "decisions": rows,
                            "portfolio_summary": "Recorded HOLD/WAIT; no trade required",
                        }
                    ),
                }
            ]
        )
    raise RuntimeError("Replay transport attempted external authorization/catalog I/O")


@asynccontextmanager
async def lifespan(application):
    global pinned
    if MODE == "replay":
        state = native.store.read()
        state.github_token, state.access_token = SecretStr("fake-gh"), SecretStr(
            "fake-cp"
        )
        import time

        state.expires_at = time.time() + 3600
        state.catalog_at = time.time()
        state.selected_model = "gpt-6-astra"
        state.role_models = {}
        state.models = [CopilotModel(id="gpt-6-astra", name="Recorded Astra")]
        native.store.save(state)
    state = native.store.read()
    pinned = (
        state.generation,
        state.routing_revision,
        state.role_models.get("portfolio_decisions", state.selected_model),
    )
    if pinned[2] != "gpt-6-astra":
        raise RuntimeError("Authorized Astra role is not configured; no inference")
    async with original_lifespan(application):
        budget = Budget(application.state.mongodb, RUN_ID, MODE)
        application.state.acceptance_budget = budget
        native.transport = GuardedTransport(
            budget,
            (
                httpx.AsyncHTTPTransport(retries=0)
                if MODE == "live"
                else httpx.MockTransport(recorded)
            ),
            authorize,
        )
        yield


app.router.lifespan_context = lifespan


@app.middleware("http")
async def inference_scope(request: Request, call_next):
    # Even trusted-local fixture callers cannot reset/change the shared native
    # credentials, start research/chat inference, or create another paid lane.
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and not (
        request.url.path.startswith("/api/test/model-portfolios/")
        or request.url.path == "/api/portfolio/model-decisions"
        or (
            request.url.path.startswith("/api/portfolio/review-batches/")
            and request.url.path.endswith("/approve")
        )
    ):
        return JSONResponse(
            {"detail": "Mutation outside acceptance scope"}, status_code=403
        )
    if (
        request.url.path == "/api/portfolio/model-decisions"
        and request.method == "POST"
    ):
        if not active:
            return JSONResponse(
                {"detail": "Seed a registered acceptance case first"}, status_code=409
            )
        body = await request.json()
        if body.get("assessment_id") != active["source"]["assessment_id"]:
            return JSONResponse(
                {"detail": "Acceptance source scope mismatch"}, status_code=409
            )
        token = CURRENT_CASE.set(active["case_id"])
        try:
            state = await app.state.acceptance_budget.state()
            from datetime import UTC, datetime

            remaining = max(
                0,
                (
                    datetime.fromisoformat(state["deadline"]) - datetime.now(UTC)
                ).total_seconds(),
            )
            async with asyncio.timeout(min(90, remaining)):
                return await call_next(request)
        finally:
            CURRENT_CASE.reset(token)
    return await call_next(request)


async def skip_warming(self, symbols=None):
    return {"status": "disabled", "reason": "synthetic_acceptance_no_market_io"}


async def quote(self, symbol):
    from datetime import UTC, datetime
    from src.services.portfolio_risk.calendar import completed_session

    return QuoteData(
        symbol=symbol,
        price=100.0,
        volume=1000000,
        previous_close=100.0,
        latest_trading_day=str(completed_session(datetime.now(UTC))),
        change=0.0,
        change_percent=0.0,
        open=100.0,
        high=100.0,
        low=100.0,
        session="closed",
        source="synthetic-acceptance",
        asof=datetime.now(UTC),
    )


async def movers():
    return {
        "top_gainers": [],
        "top_losers": [],
        "most_actively_traded": [],
        "source": "synthetic-acceptance",
    }


yf.Ticker = SyntheticTicker
CacheWarmingService.warm_startup_cache = skip_warming
FinnhubService.fetch_quote = quote
yfinance_movers.get_market_movers = movers


@app.post("/api/test/model-portfolios/register", dependencies=[Depends(local_action)])
async def register():
    await app.state.acceptance_budget.register()
    return {"mode": MODE, "run_id": RUN_ID, "manifest": manifest()}


@app.post(
    "/api/test/model-portfolios/seed/{identifier}", dependencies=[Depends(local_action)]
)
async def seed_case(identifier: str):
    case(identifier)
    registered = await app.state.acceptance_budget.state()
    if MODE == "live" and any(
        a["case_id"] == identifier for a in registered["attempts"]
    ):
        raise HTTPException(
            409, "Paid case already attempted; retain its report, no reseeding"
        )
    from src.api.dependencies.rate_limit import limiter

    limiter.reset()  # isolated fixture scenarios, not a production limit change
    source = await seed(app.state.mongodb, identifier, RUN_ID)
    active.clear()
    active.update(
        case_id=identifier,
        source=source,
        baseline=await ledger_hashes(app.state.mongodb),
    )
    return source


@app.post(
    "/api/test/model-portfolios/observe/{identifier}",
    dependencies=[Depends(local_action)],
)
async def observe_case(identifier: str):
    if active.get("case_id") != identifier:
        raise HTTPException(409, "Observe the current registered case only")
    return await observe(
        app.state.mongodb,
        app.state.acceptance_budget,
        identifier,
        active["source"]["assessment_id"],
        active["baseline"],
    )


@app.get("/api/test/model-portfolios/report", dependencies=[Depends(no_store)])
async def report():
    value = await app.state.acceptance_budget.state()
    value.pop("_id", None)
    value["inference_attempt_count"] = len(value["attempts"])
    value["cost_usd"] = None
    value["cost_basis"] = "unknown Copilot allowance pricing; no fabricated dollar cost"
    return value
