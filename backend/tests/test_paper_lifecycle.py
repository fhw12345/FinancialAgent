"""Paper CAS/replay/failure/stale/read-only boundaries with real production accounting."""

import asyncio
from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.services.paper_ledger import service, store, valuation
from tests.paper_fixtures import Clock, NOW, action, creation, journal, refresh, setup
from tests.review_fixtures import market_asset


@pytest.mark.asyncio
async def test_replay_100_times_close_and_changed_request_never_repeat_fee(monkeypatch):
    db = setup(monkeypatch)
    create = creation(commission_bps="10")
    identifier = (await service.create(db, create)).experiment.experiment_id
    body = journal(1)
    expected = await service.journal(db, identifier, body)
    for _ in range(100):
        assert (
            await service.journal(db, identifier, body)
        ).experiment == expected.experiment
    assert (await service.create(db, create)).experiment.sequence == 2
    with pytest.raises(store.PaperConflict, match="different inputs"):
        await service.create(db, creation(initial_cash="20000"))
    with pytest.raises(store.PaperConflict, match="different inputs"):
        await service.journal(db, identifier, journal(1, quantity="20"))
    with pytest.raises(store.PaperConflict, match="changed"):
        await service.journal(db, identifier, journal(1, "stale-sequence"))
    closed = await service.journal(
        db, identifier, action(2, "close-paper", {"kind": "close"})
    )
    assert closed.projection.closed
    assert (await service.journal(db, identifier, body)).experiment.sequence == 3
    with pytest.raises(store.PaperConflict, match="closed"):
        await service.journal(db, identifier, journal(3, "after-close"))
    assert (await service.recent(db))[0].closed
    assert expected.projection.commissions == Decimal("1.00")


@pytest.mark.asyncio
async def test_competing_buys_do_not_overdraw_or_commit_two_events(monkeypatch):
    db = setup(monkeypatch)
    identifier = (
        await service.create(db, creation(slippage_bps="0"))
    ).experiment.experiment_id
    results = await asyncio.gather(
        *[
            service.journal(
                db, identifier, journal(1, f"competing-buy-{i}", quantity="60")
            )
            for i in range(2)
        ],
        return_exceptions=True,
    )
    assert sum(not isinstance(r, Exception) for r in results) == 1
    assert sum(isinstance(r, store.PaperConflict) for r in results) == 1
    assert (await service.get(db, identifier)).projection.cash == Decimal("4000")


@pytest.mark.asyncio
async def test_reads_startup_and_replays_do_no_model_or_provider_io(monkeypatch):
    db = setup(monkeypatch)
    identifier = (await service.create(db, creation())).experiment.experiment_id
    await service.journal(db, identifier, journal(1))
    assert (await service.get(db, identifier)).valuation is None
    assert len(await service.recent(db)) == 1
    assert (await store.get(db, identifier)).sequence == 2
    valuation.provider.fetch_asset.assert_not_awaited()
    body = refresh(2)
    marked = await service.refresh(db, identifier, body)
    calls = valuation.provider.fetch_asset.await_count
    assert (await service.refresh(db, identifier, body)).experiment == marked.experiment
    assert valuation.provider.fetch_asset.await_count == calls
    Clock.value = NOW + timedelta(days=7)
    reopened = await service.get(db, identifier)
    assert reopened.valuation.stale and reopened.valuation.nav == Decimal("9999")
    assert "VALUATION_SESSION_CHANGED" in reopened.valuation.stale_reasons
    assert valuation.provider.fetch_asset.await_count == calls


@pytest.mark.asyncio
async def test_missing_currency_history_price_and_marks_do_not_become_zero_nav(
    monkeypatch,
):
    db = setup(monkeypatch)
    identifier = (
        await service.create(db, creation(slippage_bps="0"))
    ).experiment.experiment_id
    await service.journal(db, identifier, journal(1))
    await service.journal(
        db, identifier, journal(2, "second-symbol", symbol="MSFT", quantity="5")
    )
    for index, changes in enumerate(
        (
            {"errors": ["missing"]},
            {"currency": "EUR"},
            {"mark": None},
            {"mark": 0.00000001},
        )
    ):
        valuation.provider.fetch_asset.side_effect = (
            lambda symbol, session: market_asset(symbol).model_copy(
                update=changes if symbol == "MSFT" else {}
            )
        )
        marked = await service.refresh(
            db, identifier, refresh(index + 3, f"missing-mark-{index}")
        )
        assert marked.valuation.status == "unavailable" and marked.valuation.nav is None
        assert marked.valuation.scenario_pnl is None
        assert (
            marked.valuation.marked_positions == 1
            and marked.valuation.total_positions == 2
        )
        assert any("MSFT" in e for e in marked.valuation.errors)


@pytest.mark.asyncio
async def test_provider_and_storage_failure_no_false_success_or_repeat_account_changes(
    monkeypatch,
):
    db = setup(monkeypatch)
    identifier = (await service.create(db, creation())).experiment.experiment_id
    await service.journal(db, identifier, journal(1))
    original = valuation.provider.fetch_asset.side_effect
    valuation.provider.fetch_asset.side_effect = RuntimeError(
        "unexpected storage/transport fault"
    )
    with pytest.raises(RuntimeError):
        await service.refresh(db, identifier, refresh(2))
    assert (await store.get(db, identifier)).sequence == 2
    valuation.provider.fetch_asset.side_effect = original
    collection = db.get_collection(store.COLLECTION)
    write = collection.find_one_and_update
    collection.find_one_and_update = AsyncMock(side_effect=RuntimeError("disk full"))
    with pytest.raises(RuntimeError):
        await service.journal(db, identifier, journal(2, "storage-sale", side="sell"))
    assert (await store.get(db, identifier)).sequence == 2
    collection.find_one_and_update = write
    saved = await service.journal(
        db, identifier, journal(2, "storage-sale", side="sell")
    )
    assert saved.experiment.sequence == 3 and saved.projection.positions == []


@pytest.mark.asyncio
@pytest.mark.parametrize("race", ["ledger", "clock", "deadline"])
async def test_valuation_publication_rejects_input_or_session_changes(
    monkeypatch, race
):
    db = setup(monkeypatch)
    identifier = (await service.create(db, creation())).experiment.experiment_id
    await service.journal(db, identifier, journal(1))
    fetch = valuation.provider.fetch_asset.side_effect

    async def racing(symbol, session):
        if race == "ledger":
            await service.journal(
                db, identifier, journal(2, "racing-sale", side="sell", quantity="1")
            )
        elif race == "clock":
            Clock.value = NOW + timedelta(days=7)
        else:
            db.now = NOW + timedelta(days=7)  # app precheck still says valid
        return fetch(symbol, session)

    valuation.provider.fetch_asset.side_effect = racing
    with pytest.raises(store.PaperConflict):
        await service.refresh(db, identifier, refresh(2))
    saved = await service.get(db, identifier)
    assert saved.valuation is None and saved.experiment.sequence == (
        3 if race == "ledger" else 2
    )


@pytest.mark.asyncio
async def test_hash_tampering_and_invalid_actions_are_fail_closed(monkeypatch):
    db = setup(monkeypatch)
    identifier = (await service.create(db, creation())).experiment.experiment_id
    await service.journal(db, identifier, journal(1, quantity="0.1"))
    for entry, code in [
        (
            {"kind": "split", "symbol": "AAPL", "numerator": 1, "denominator": 3},
            "SPLIT_QUANTITY_PRECISION",
        ),
        (
            {"kind": "split", "symbol": "MSFT", "numerator": 2, "denominator": 1},
            "HOLDING_REQUIRED",
        ),
        (
            {
                "kind": "dividend",
                "symbol": "AAPL",
                "gross_per_share": "1",
                "withholding": "1",
            },
            "WITHHOLDING",
        ),
        (
            {
                "kind": "dividend",
                "symbol": "MSFT",
                "gross_per_share": "1",
                "withholding": "0",
            },
            "HOLDING_REQUIRED",
        ),
    ]:
        with pytest.raises(store.PaperConflict, match=code):
            await service.journal(db, identifier, action(2, "bad-action", entry))
    row = db.get_collection(store.COLLECTION).rows[identifier]
    row["events"][1]["payload"]["quantity"] = "1000"
    with pytest.raises(store.PaperConflict, match="INTEGRITY"):
        await service.get(db, identifier)
