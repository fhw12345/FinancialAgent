"""In-memory outer storage/market transports; production evidence lifecycle and validators run unchanged."""

import asyncio
import copy
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from pymongo.errors import DuplicateKeyError
from src.services.evidence.context import frozen_result
from tests.portfolio_risk_fixtures import snapshot as risk_snapshot, asset, ASOF


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def limit(self, n):
        self.rows = self.rows[:n]
        return self

    def sort(self, *args, **kwargs):
        return self

    async def __aiter__(self):
        for row in self.rows:
            yield copy.deepcopy(row)


class Collection:
    def __init__(self, db):
        self.database = db
        self.rows = {}
        self.lock = asyncio.Lock()

    async def create_index(self, *args, **kwargs):
        return "run_id_1"

    def matches(self, row, query):
        return all(row.get(key) == value for key, value in query.items())

    async def find_one(self, query, **kwargs):
        return next(
            (copy.deepcopy(r) for r in self.rows.values() if self.matches(r, query)),
            None,
        )

    def find(self, query):
        return Cursor([r for r in self.rows.values() if self.matches(r, query)])

    async def find_one_and_update(self, query, update, upsert=False, **kwargs):
        async with self.lock:
            row = await self.find_one(query)
            if row is None:
                if not upsert:
                    return None
                if query["_id"] in self.rows:
                    raise DuplicateKeyError("duplicate")
                row = {**query, **copy.deepcopy(update.get("$setOnInsert", {}))}
            row.update(copy.deepcopy(update.get("$set", {})))
            self.rows[row["_id"]] = row
            return copy.deepcopy(row)

    async def update_one(self, query, update, **kwargs):
        return await self.find_one_and_update(query, update, **kwargs)


class Database:
    def __init__(self):
        self.collections = {}

    def get_collection(self, name):
        return self.collections.setdefault(name, Collection(self))


def market():
    return SimpleNamespace(
        get_company_overview=AsyncMock(
            side_effect=lambda symbol: {
                "Symbol": symbol,
                "Currency": "USD",
                "FinancialCurrency": "USD",
                "Exchange": "NASDAQ",
                "PERatio": "20",
                "EPS": "5",
                "_source": "yfinance",
            }
        ),
        get_cash_flow=AsyncMock(return_value={}),
        get_balance_sheet=AsyncMock(return_value={}),
    )


def manager():
    return SimpleNamespace(
        _av_service=market(),
        get_quote=AsyncMock(
            return_value=SimpleNamespace(
                price=100,
                source="finnhub",
                session="closed",
                latest_trading_day="2026-09-16",
            )
        ),
        get_ohlcv=AsyncMock(return_value=[]),
        get_company_news=AsyncMock(return_value=[]),
        get_insider_trades=AsyncMock(return_value=[]),
    )


def claim_block(symbol):
    payload = json.loads(frozen_result("get_stock_quote", {"symbol": symbol}))
    rows = payload.get("records", [])
    if not rows:
        return ""
    row = next(r for r in rows if r["metric"] == "price.close_reference")
    return (
        "<claims-json>"
        + json.dumps(
            {
                "claims": [
                    {
                        "kind": "fact",
                        "symbol": symbol,
                        "metric": row["metric"],
                        "value": row["value"],
                        "unit": row["unit"],
                        "period": row["period"],
                        "period_end": row["period_end"],
                        "evidence_ids": [row["evidence_id"]],
                    }
                ]
            }
        )
        + "</claims-json>"
    )


def setup_deep(monkeypatch):
    """Supply newly required outer dependencies to pre-existing pure graph tests."""
    from src.services.evidence import service
    from src.services.decision_policy.context import assessment_run

    original = service.run_deep
    db = Database()

    async def run(agent, workflow, state, config, symbol):
        agent._order_repo = SimpleNamespace(
            collection=db.get_collection("portfolio_orders")
        )
        agent._data_manager = manager()
        with assessment_run("deep_test"):
            return await original(agent, workflow, state, config, symbol)

    monkeypatch.setattr(service, "run_deep", run)
    monkeypatch.setattr(
        service.risk_service,
        "capture",
        AsyncMock(
            side_effect=lambda db, symbols: risk_snapshot(
                holdings={}, assets=[asset(s) for s in symbols]
            )
        ),
    )

    async def summary(*args, **kwargs):
        from src.models.evidence import EvidenceSummary

        return EvidenceSummary(
            snapshot_ids=["unit_snapshot"], dossier_ids=["unit_dossier"], errors=[]
        )

    monkeypatch.setattr(service, "deep_summary", summary)
