"""Real BSON wire shape and service policy CAS / capture failure behavior."""

import asyncio
import copy
from unittest.mock import AsyncMock, MagicMock
from bson import BSON
from pymongo.errors import DuplicateKeyError
import pytest
from src.models.portfolio_risk import PortfolioRiskReview
from src.database.repositories.decision_assessment_repository import (
    DecisionAssessmentRepository,
)
from src.services.portfolio_risk import service, provider
from src.services.portfolio_risk.estimator import estimate
from tests.portfolio_risk_fixtures import snapshot, policy, asset, ASOF


@pytest.mark.asyncio
async def test_assessment_receipt_is_bson_serializable_and_dates_roundtrip():
    s = snapshot()
    review = PortfolioRiskReview(snapshot=s, current=estimate(s))
    collection = MagicMock()

    async def write(query, update, **kw):
        return BSON(BSON.encode(update["$setOnInsert"])).decode()

    collection.find_one_and_update = AsyncMock(side_effect=write)
    result = await DecisionAssessmentRepository(collection).assess_and_persist(
        request_key="bson",
        source="holdings",
        symbols=["AAPL"],
        proposals=[],
        portfolio_risk=review,
    )
    assert result.portfolio_risk.snapshot.session_date == ASOF
    assert (
        result.portfolio_risk.current.common_sessions == review.current.common_sessions
    )
    assert not result.actionable


class PolicyCollection:
    def __init__(self):
        self.doc = None
        self.lock = asyncio.Lock()

    async def find_one(self, query, **kw):
        return copy.deepcopy(self.doc)

    async def find_one_and_update(self, query, update, **kw):
        async with self.lock:
            if self.doc is not None and self.doc["revision"] != query["revision"]:
                if kw["upsert"]:
                    raise DuplicateKeyError("revision conflict")
                return None
            self.doc = copy.deepcopy(update["$set"])
            return copy.deepcopy(self.doc)


@pytest.mark.asyncio
async def test_whole_policy_cas_and_no_implicit_personal_defaults():
    collection = PolicyCollection()
    from tests.evidence_fixtures import Database

    control_db = Database()
    mongo = MagicMock()
    mongo.get_collection.side_effect = lambda name: (
        collection if name == "risk_policy" else control_db.get_collection(name)
    )
    assert (await service.policy_state(mongo)).policy is None
    p = policy().policy
    outcomes = await asyncio.gather(
        *(service.confirm_policy(mongo, p, 0) for _ in range(5)), return_exceptions=True
    )
    assert sum(isinstance(x, service.RiskConflict) for x in outcomes) == 4
    assert (await service.policy_state(mongo)).revision == 1
    await service.confirm_policy(mongo, p, 1)
    with pytest.raises(service.RiskConflict):
        await service.confirm_policy(mongo, p, 1)


@pytest.mark.asyncio
async def test_capture_account_race_is_not_a_complete_risk_snapshot(monkeypatch):
    s = snapshot()
    monkeypatch.setattr(
        service,
        "account",
        AsyncMock(
            side_effect=[(s.positions, s.cash, "one"), (s.positions, s.cash, "two")]
        ),
    )
    monkeypatch.setattr(service, "policy_state", AsyncMock(return_value=s.policy))
    monkeypatch.setattr(service, "completed_session", lambda now: ASOF)
    monkeypatch.setattr(provider, "fetch_asset", AsyncMock(return_value=asset()))
    captured = await service.capture(MagicMock())
    assert "ACCOUNT_CHANGED_DURING_CAPTURE" in captured.errors
    assert estimate(captured).status == "unavailable"


@pytest.mark.asyncio
async def test_refresh_failure_and_stale_policy_never_report_new_saved_success(
    monkeypatch,
):
    s = snapshot()
    monkeypatch.setattr(service, "capture", AsyncMock(return_value=s))
    mongo = MagicMock()
    mongo.get_collection.return_value.create_index = AsyncMock()
    mongo.get_collection.return_value.find_one_and_update = AsyncMock(
        side_effect=RuntimeError("storage offline")
    )
    with pytest.raises(RuntimeError):
        await service.review_current(mongo)
    monkeypatch.setattr(
        service, "account", AsyncMock(return_value=(s.positions, s.cash, "changed"))
    )
    monkeypatch.setattr(service, "policy_state", AsyncMock(return_value=policy()))
    monkeypatch.setattr(service, "completed_session", lambda now: ASOF)
    projected = await service.project_stale(
        mongo, PortfolioRiskReview(snapshot=s, current=estimate(s))
    )
    assert projected.stale and set(projected.stale_reasons) == {
        "ACCOUNT_CHANGED",
        "POLICY_CHANGED",
    }
    assert s.account_revision == "fixture"


@pytest.mark.asyncio
async def test_provider_missing_or_nan_adjusted_prices_are_unavailable(monkeypatch):
    import pandas as pd
    from types import SimpleNamespace
    from src.services.portfolio_risk.calendar import sessions

    frame = pd.DataFrame(
        {"Close": [100.0] * 61, "Adj Close": [100.0] * 60 + [float("nan")]},
        index=pd.to_datetime(sessions(ASOF, 61)),
    )
    ticker = SimpleNamespace(
        info={
            "currency": "USD",
            "quoteType": "EQUITY",
            "sector": "Technology",
            "beta": 1.0,
        },
        history=lambda **kw: frame,
    )
    monkeypatch.setattr(provider.yf, "Ticker", lambda symbol: ticker)
    result = await provider.fetch_asset("AAPL", ASOF)
    assert result.errors == ["INVALID_ADJUSTED_PRICE"]
    ticker.info["quoteType"] = "CRYPTOCURRENCY"
    assert (await provider.fetch_asset("AAPL", ASOF)).errors == [
        "INSTRUMENT_UNSUPPORTED_OR_UNKNOWN"
    ]
