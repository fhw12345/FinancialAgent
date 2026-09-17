"""Existing provider/data-manager boundaries are consumed once; cancellation/storage remain explicit."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock
import pytest
from src.database.repositories.evidence_repository import (
    EvidenceRepository,
    EvidenceConflict,
)
from src.services.evidence.collection import collect
from src.services.evidence import adapters
from src.services.evidence.claims import validate_claim
from src.models.evidence import ResearchClaim
from tests.evidence_fixtures import Database, manager
from tests.portfolio_risk_fixtures import snapshot as risk_snapshot
from tests.test_evidence_claims import snapshot, record, claim, NOW


@pytest.mark.asyncio
async def test_complete_sealed_retry_reuses_bytes_not_new_provider_data():
    db = Database()
    repo = EvidenceRepository(db)
    dm = manager()
    risk = risk_snapshot()

    async def collect_once():
        return await collect(
            repo,
            request_key="one",
            run_id="run",
            symbol="AAPL",
            as_of=NOW,
            data_manager=dm,
            market_service=dm._av_service,
            risk=risk,
        )

    before = await collect_once()
    dm.get_quote.side_effect = RuntimeError("provider changed")
    after = await collect_once()
    assert before.model_dump(mode="json") == after.model_dump(mode="json")
    dm.get_quote.assert_awaited_once()
    dm._av_service.get_company_overview.assert_awaited_once()
    assert any(
        r.provider == "yfinance" for r in before.records if r.family == "overview"
    )


@pytest.mark.asyncio
async def test_provider_failure_is_a_missing_record_not_repeated_or_success():
    db = Database()
    repo = EvidenceRepository(db)
    dm = manager()
    dm.get_quote.side_effect = RuntimeError("token=must-not-leak")
    dm._av_service.get_company_overview.side_effect = RuntimeError("secret")
    result = await collect(
        repo,
        request_key="one",
        run_id="run",
        symbol="AAPL",
        as_of=NOW,
        data_manager=dm,
        market_service=dm._av_service,
    )
    assert (
        result.state == "sealed"
        and result.coverage["quote"] == "missing"
        and result.coverage["overview"] == "missing"
    )
    assert "must-not-leak" not in result.model_dump_json()
    dm.get_quote.assert_awaited_once()
    assert result.coverage["news"] == "missing"
    assert result.coverage["filing"] == "missing"


@pytest.mark.asyncio
async def test_cancelled_collector_and_failed_seal_never_publish_success():
    db = Database()
    repo = EvidenceRepository(db)
    dm = manager()
    started = asyncio.Event()

    async def pause(*args, **kw):
        started.set()
        await asyncio.Event().wait()

    dm.get_quote = AsyncMock(side_effect=pause)
    task = asyncio.create_task(
        collect(
            repo,
            request_key="one",
            run_id="run",
            symbol="AAPL",
            as_of=NOW,
            data_manager=dm,
            market_service=dm._av_service,
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    row = next(iter(db.get_collection("research_snapshots").rows.values()))
    assert row["state"] == "cancelled"
    with pytest.raises(EvidenceConflict):
        await repo.get(row["snapshot_id"])
    dm = manager()
    repo.finish = AsyncMock(side_effect=RuntimeError("disk unavailable"))
    with pytest.raises(RuntimeError):
        await collect(
            repo,
            request_key="two",
            run_id="run",
            symbol="AAPL",
            as_of=NOW,
            data_manager=dm,
            market_service=dm._av_service,
        )
    assert sorted(
        r["state"] for r in db.get_collection("research_snapshots").rows.values()
    ) == ["cancelled", "failed"]


def test_weekend_close_vs_delayed_intraday_does_not_use_retrieval_as_observation():
    s = snapshot()
    s.requested_as_of = datetime(2026, 9, 19, 12, tzinfo=UTC)
    r = record(period_end=datetime(2026, 9, 18).date())
    s.records = [r]
    assert validate_claim(s, claim(r)).status == "matches_snapshot"
    live = record(metric="price.last", period="instant", observed_at=None)
    s.records = [live]
    assert (
        "QUOTE_FRESHNESS_POLICY_UNCONFIRMED" in validate_claim(s, claim(live)).reasons
    )


def test_statement_and_filing_adapters_preserve_unknown_publication_and_units():
    s = snapshot()
    records = adapters.statements(
        s,
        "cash_flow",
        {
            "_source": "alphavantage",
            "quarterlyReports": [
                {
                    "fiscalDateEnding": "2026-06-30",
                    "reportedCurrency": "USD",
                    "operatingCashflow": "100",
                    "capitalExpenditures": "20",
                }
            ],
        },
    )
    assert (
        records[0].unit == "USD"
        and records[0].period == "quarter"
        and records[0].published_at is None
    )
    filing = adapters.filings(
        s,
        [
            {
                "_source": "sec",
                "shares": 10,
                "transactionDate": "2026-06-30",
                "source_url": "https://www.sec.gov/Archives/test.xml?token=hidden",
            }
        ],
    )[0]
    assert (
        filing.unit == "shares"
        and filing.published_at is None
        and filing.point_in_time_status != "verified"
    )
    assert filing.source_uri == "https://www.sec.gov/Archives/test.xml"
