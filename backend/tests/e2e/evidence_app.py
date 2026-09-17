"""Real evidence/graph/API/storage acceptance; only external receipts and clock are recorded."""

from datetime import UTC, datetime
from src.services import agent_run_service, market_data
from src.api import portfolio_admin
from src.services.finnhub.service import FinnhubService
from src.services.data_manager.types import QuoteData
from src.services.portfolio_risk import service as risk_service
from tests.e2e.decision_policy_app import app, reset, service, model_transport
from tests.copilot_fixtures import sse, text_output
import json
import httpx

mode = "normal"


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)


async def deep_transport(request):
    body = json.loads(request.content)
    names = [tool.get("name") for tool in body.get("tools", [])]
    if "DeepVerdict" in names:
        records = []
        for text in strings(body.get("input", [])):
            for line in text.splitlines():
                try:
                    payload = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if isinstance(payload, dict):
                    records.extend(payload.get("records", []))
        record = next(
            r
            for r in records
            if r.get("metric") == "price.close_reference"
            and r.get("quality") == "available"
        )
        assertion = {
            key: record[key]
            for key in ["symbol", "metric", "value", "unit", "period", "period_end"]
        }
        report = (
            "## Recorded Deep evidence\nAction: HOLD\n<claims-json>"
            + json.dumps(
                {
                    "claims": [
                        {
                            **assertion,
                            "kind": "fact",
                            "evidence_ids": [record["evidence_id"]],
                        }
                    ]
                }
            )
            + "</claims-json>"
        )
        return sse(
            [
                {
                    "type": "function_call",
                    "call_id": "verdict",
                    "name": "DeepVerdict",
                    "arguments": json.dumps(
                        {
                            "report_markdown": report,
                            "action": "HOLD",
                            "conviction": "LOW",
                            "risk_level": "MODERATE",
                            "key_insight": "Recorded evidence only",
                            "concern_assessments": [],
                        }
                    ),
                }
            ]
        )
    if any("NO FURTHER CONCERNS" in text for text in strings(body.get("input", []))):
        return sse(text_output("NO FURTHER CONCERNS"))
    return await model_transport(request)


service.transport = httpx.MockTransport(deep_transport)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 9, 17, 12, tzinfo=UTC)


market_data.get_market_session = lambda *args, **kwargs: "closed"
risk_service.datetime = Clock
agent_run_service.utcnow = lambda: Clock.now(UTC)
portfolio_admin.utcnow = lambda: Clock.now(UTC)


async def quote(self, symbol):
    return QuoteData(
        symbol=symbol,
        price=101.0 if mode == "conflict" else 100.0,
        volume=1000000,
        latest_trading_day="2026-09-16",
        previous_close=99.0,
        change=1.0,
        change_percent=1.01,
        open=99.0,
        high=102.0,
        low=98.0,
        session="closed",
        source="finnhub",
        asof=Clock.now(UTC),
    )


async def no_news(self, *args, **kwargs):
    return []


FinnhubService.fetch_quote = quote
FinnhubService.fetch_company_news = no_news
FinnhubService.fetch_insider_transactions = no_news


@app.post("/api/test/evidence/change-provider")
async def change_provider():
    global mode
    mode = "conflict"
    from src.services.data_manager import CacheKeys

    await app.state.redis.delete(CacheKeys.quote("AAPL"))
    return {"changed": True}


@app.post("/api/test/evidence/reset/{scenario}")
async def reset_evidence(scenario: str):
    global mode
    assert scenario in ("normal", "conflict")
    mode = scenario
    await reset("good")
    return {"reset": True}
