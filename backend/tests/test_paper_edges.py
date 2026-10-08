"""No false success at valuation arithmetic, storage bounds and cancellation boundaries."""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest

from src.models.paper_ledger import InitialInput, PaperExperiment, ValuationInput
from src.services.paper_ledger import service, store, valuation
from tests.paper_fixtures import creation, journal, refresh, setup
from tests.review_fixtures import market_asset


@pytest.mark.asyncio
async def test_valuation_overflow_is_a_durable_unavailable_receipt_not_a_broken_account(
    monkeypatch,
):
    db = setup(monkeypatch)
    identifier = (
        await service.create(
            db, creation(initial_cash="1000000000000000", slippage_bps="0")
        )
    ).experiment.experiment_id
    await service.journal(
        db, identifier, journal(1, quantity="1000000000", reference_price="1")
    )
    valuation.provider.fetch_asset.side_effect = lambda symbol, session: market_asset(
        symbol
    ).model_copy(update={"mark": 1000000000.0})
    result = await service.refresh(db, identifier, refresh(2))
    assert result.valuation.status == "unavailable" and result.valuation.nav is None
    assert "VALUATION_MONEY_RANGE_EXCEEDED:AAPL" in result.valuation.errors
    assert (await service.get(db, identifier)).valuation == result.valuation
    assert result.projection.positions[0].quantity == Decimal("1000000000")


@pytest.mark.asyncio
async def test_parallel_duplicate_request_returns_one_committed_event(monkeypatch):
    db = setup(monkeypatch)
    identifier = (await service.create(db, creation())).experiment.experiment_id
    original = store.append
    rendezvous = asyncio.Event()
    arrivals = 0

    async def together(db, current, addition, deadline=None):
        nonlocal arrivals
        arrivals += 1
        if arrivals == 2:
            rendezvous.set()
        await rendezvous.wait()
        return await original(db, current, addition, deadline)

    monkeypatch.setattr(store, "append", together)
    answers = await asyncio.gather(
        *(service.journal(db, identifier, journal(1)) for _ in range(2))
    )
    assert [a.experiment.sequence for a in answers] == [2, 2]
    assert len((await service.get(db, identifier)).experiment.events) == 2


@pytest.mark.asyncio
async def test_cancelled_valuation_and_wrong_session_do_not_append_events(monkeypatch):
    db = setup(monkeypatch)
    identifier = (await service.create(db, creation())).experiment.experiment_id
    await service.journal(db, identifier, journal(1))
    wrong = refresh(2).model_copy(
        update={"session_date": refresh(2).session_date.replace(day=16)}
    )
    with pytest.raises(store.PaperConflict, match="current completed"):
        await service.refresh(db, identifier, wrong)
    reached = asyncio.Event()

    async def hanging(*args):
        reached.set()
        await asyncio.Event().wait()

    valuation.provider.fetch_asset = AsyncMock(side_effect=hanging)
    task = asyncio.create_task(service.refresh(db, identifier, refresh(2)))
    await reached.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await service.get(db, identifier)).experiment.sequence == 2


@pytest.mark.asyncio
async def test_invalid_recomputed_projection_and_large_aggregate_cannot_write(
    monkeypatch,
):
    db = setup(monkeypatch)
    current = (await service.create(db, creation())).experiment
    initial = store.event(
        current.experiment_id,
        2,
        "duplicate-created",
        "hash",
        InitialInput(settings=creation().settings),
        current.events[-1].event_hash,
    )
    with pytest.raises(store.PaperConflict, match="DUPLICATE_INITIAL_STATE"):
        await store.append(db, current, initial)
    # The byte-boundary test supplies a valid chain but a bounded-input encoded
    # representation over budget; no weakened event integrity or phantom success.
    original_dumps = store.json.dumps
    monkeypatch.setattr(
        store,
        "json",
        SimpleNamespace(
            dumps=lambda *a, **kw: original_dumps(*a, **kw) + " " * (2 * 1024 * 1024)
        ),
    )
    addition = store.event(
        current.experiment_id,
        2,
        "large-journal",
        "hash",
        journal(1).entry,
        current.events[-1].event_hash,
    )
    with pytest.raises(store.PaperConflict, match="2 MiB"):
        await store.append(db, current, addition)
    assert (await store.get(db, current.experiment_id)).sequence == 1


def test_corrupt_valuation_scope_and_nav_sum_overflow_have_no_complete_result(
    monkeypatch,
):
    setup(monkeypatch)
    made = store.event(
        "paper_test",
        1,
        "initial-test",
        "hash",
        InitialInput(settings=creation(initial_cash="1000000000000000").settings),
        "",
    )
    bought = store.event(
        "paper_test",
        2,
        "bought-test",
        "hash",
        journal(1, quantity="1", reference_price="1").entry,
        made.event_hash,
    )
    from src.models.paper_ledger import ClosingMark

    valued = store.event(
        "paper_test",
        3,
        "valued-test",
        "hash",
        ValuationInput(
            session_date="2026-09-17",
            ledger_sequence=2,
            fetched_at=made.recorded_at,
            reconciliation="corporate-actions-inspected-through-this-session",
            marks=[
                ClosingMark(
                    symbol="AAPL",
                    session_date="2026-09-17",
                    price="1000000000",
                    currency="USD",
                    source="recorded",
                )
            ],
        ),
        bought.event_hash,
    )
    receipt = valuation.receipt([made, bought, valued])
    assert receipt.status == "unavailable" and receipt.nav is None
    valued.payload.marks = []
    assert (
        "VALUATION_POSITION_SCOPE_MISMATCH"
        in valuation.receipt([made, bought, valued]).errors
    )
    assert (
        PaperExperiment(
            experiment_id="paper_test", sequence=3, events=[made, bought, valued]
        ).sequence
        == 3
    )
