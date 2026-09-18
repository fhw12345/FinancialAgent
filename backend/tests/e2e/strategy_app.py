"""Strategy acceptance with recorded outer financials/model receipts and actual app/storage."""

import json
import pandas as pd
import httpx
import yfinance as yf
from tests.e2e.evidence_app import app, service, reset_evidence, deep_transport, strings
from tests.e2e.decision_policy_app import RecordedTicker
from tests.copilot_fixtures import sse

mode = "normal"


class StrategyTicker(RecordedTicker):
    @property
    def info(self):
        return {
            **super().info,
            "country": "United States",
            "industry": "Recorded industry",
            "financialCurrency": "USD",
            "longName": "Recorded Company",
        }

    @property
    def cashflow(self):
        return pd.DataFrame(
            {
                "2025-12-31": {
                    "Operating Cash Flow": 150000000.0,
                    "Capital Expenditure": -50000000.0,
                    "Net Income": 50000000.0,
                }
            }
        ).rename(columns=pd.Timestamp)

    @property
    def quarterly_cashflow(self):
        return pd.DataFrame()

    @property
    def balance_sheet(self):
        return pd.DataFrame(
            {
                "2025-12-31": {
                    "Total Debt": 100000000.0,
                    "Cash And Cash Equivalents": 20000000.0,
                    "Total Assets": 500000000.0,
                    "Total Liabilities Net Minority Interest": 200000000.0,
                }
            }
        ).rename(columns=pd.Timestamp)

    @property
    def quarterly_balance_sheet(self):
        return pd.DataFrame()

    @property
    def income_stmt(self):
        return pd.DataFrame(
            {
                "2025-12-31": {
                    "Diluted EPS": float("nan") if mode == "missing" else 5.0,
                    "Diluted Average Shares": (
                        float("nan") if mode == "missing" else 10000000.0
                    ),
                    "Interest Expense": 10000000.0,
                    "Total Revenue": 200000000.0,
                    "Net Income": 50000000.0,
                }
            }
        ).rename(columns=pd.Timestamp)


yf.Ticker = StrategyTicker


async def transport(request):
    body = json.loads(request.content)
    names = [t.get("name") for t in body.get("tools", [])]
    schema = next(
        (n for n in names if n in ("StrategyConclusions", "StrategyConclusion")), None
    )
    if schema:
        views = []
        for text in strings(body.get("input", [])):
            for line in text.splitlines():
                try:
                    parsed = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if (
                    isinstance(parsed, list)
                    and parsed
                    and isinstance(parsed[0], dict)
                    and "review_id" in parsed[0]
                ):
                    views = parsed
                    break
        assert views, "Real strategy prompt must contain frozen receipts"
        conclusions = []
        for view in views:
            evidence = [
                i["evidence_id"]
                for v in view["valuations"]
                for i in v["inputs"]
                if i["symbol"] == view["symbol"]
            ]
            facts = [
                i
                for v in view["valuations"]
                for i in v["inputs"]
                if i["symbol"] == view["symbol"]
            ]
            fact = facts[0] if facts else None
            report = "Recorded strategy research, no portfolio action or execution."
            if fact:
                assertion = {
                    k: fact[k]
                    for k in [
                        "symbol",
                        "metric",
                        "value",
                        "unit",
                        "period",
                        "period_end",
                    ]
                }
                report += (
                    "<claims-json>"
                    + json.dumps(
                        {
                            "claims": [
                                {
                                    **assertion,
                                    "kind": "fact",
                                    "evidence_ids": [fact["evidence_id"]],
                                }
                            ]
                        }
                    )
                    + "</claims-json>"
                )
            conclusions.append(
                {
                    "kind": "strategy_research",
                    "symbol": view["symbol"],
                    "stance": (
                        "bullish" if view["status"] == "research_only" else "unknown"
                    ),
                    "theses": (
                        [
                            {
                                "text": "Recorded conditional research thesis",
                                "evidence_ids": evidence[:1],
                                "monitoring_rule": "earnings_decline",
                            }
                        ]
                        if evidence
                        else []
                    ),
                    "scenarios": [
                        {
                            "scenario": "base",
                            "condition": "If confirmed assumptions hold",
                            "probability": None,
                            "probability_basis": "not_estimated",
                        }
                    ],
                    "report_markdown": report,
                }
            )
        arguments = (
            {"conclusions": conclusions}
            if schema == "StrategyConclusions"
            else conclusions[0]
        )
        return sse(
            [
                {
                    "type": "function_call",
                    "name": schema,
                    "call_id": "strategy",
                    "arguments": json.dumps(arguments),
                }
            ]
        )
    return await deep_transport(request)


service.transport = httpx.MockTransport(transport)


@app.post("/api/test/strategy/reset/{scenario}")
async def reset_strategy(scenario: str):
    global mode
    assert scenario in ("normal", "missing")
    mode = scenario
    await reset_evidence("normal")
    await app.state.mongodb.get_collection("research_strategy_state").delete_many({})
    return {"reset": True}
