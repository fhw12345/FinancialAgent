"""Sealed synthetic annual statements and identity receipts for deterministic valuation tests."""

from datetime import UTC, datetime, date
from src.models.evidence import EvidenceRecord, EvidenceSnapshot
from src.services.evidence.identity import identify, manifest_hash
from tests.strategy_fixtures import version
from tests.evidence_fixtures import Database

NOW = datetime(2026, 9, 18, 12, tzinfo=UTC)


def captured(symbol="AAPL", contract=None):
    contract = contract or version()
    snap = EvidenceSnapshot(
        snapshot_id="snapshot_" + symbol,
        request_hash="req",
        run_id="run",
        symbol=symbol,
        requested_as_of=NOW,
        state="sealed",
        owner="owner",
        lease_until=NOW,
        created_at=NOW,
        strategy_version=contract.version_id,
        strategy_contract=contract,
        policy_revision=1,
        strategy_peers={"MSFT": "snapshot_MSFT"} if symbol != "MSFT" else {},
    )
    definitions = [
        ("instrument.type", "EQUITY", "text", "instant", None),
        ("instrument.country", "United States", "text", "instant", None),
        ("instrument.sector", "Technology", "text", "instant", None),
        ("instrument.industry", "Recorded peers", "text", "instant", None),
        ("price.close_reference", 100.0, "USD", "session", date(2026, 9, 17)),
        *[
            (metric, number, unit, "annual", date(2025, 12, 31))
            for metric, number, unit in [
                ("eps", 5.0, "USD/share"),
                ("net_income", 50.0, "USD"),
                ("revenue", 200.0, "USD"),
                ("operating_cash_flow", 150.0, "USD"),
                ("capital_expenditure", 50.0, "USD"),
                ("interest_expense", 10.0, "USD"),
                ("total_debt", 100.0, "USD"),
                ("cash", 20.0, "USD"),
                ("diluted_shares", 10.0, "shares"),
            ]
        ],
    ]
    snap.records = [
        identify(
            EvidenceRecord(
                snapshot_id=snap.snapshot_id,
                symbol=symbol,
                instrument_id=symbol + "@NASDAQ:USD",
                family="overview",
                metric=m,
                value=v,
                unit=u,
                period=p,
                period_end=d,
                fetched_at=NOW,
                provider="recorded",
                adapter_version="idq-005@1",
            )
        )
        for m, v, u, p, d in definitions
    ]
    snap.manifest_hash = manifest_hash(snap)
    return snap


def save(db, snap):
    snap.records = [identify(r) for r in snap.records]
    snap.manifest_hash = manifest_hash(snap)
    db.get_collection("research_snapshots").rows[snap.snapshot_id] = {
        "_id": snap.snapshot_id,
        **snap.model_dump(mode="json"),
    }


def fixture():
    db = Database()
    primary = captured()
    peer = captured("MSFT")
    save(db, primary)
    save(db, peer)
    return db, primary, peer
