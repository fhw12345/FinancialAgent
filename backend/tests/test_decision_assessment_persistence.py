import asyncio
import copy
from unittest.mock import AsyncMock, MagicMock

import pytest
from pymongo.errors import DuplicateKeyError

from src.database.repositories.decision_assessment_repository import (
    AssessmentConflict,
    DecisionAssessmentRepository,
)
from src.services.watchlist.order_handler import OrderHandler
from src.services.order_execution_service import (
    mark_order_executed,
    OrderNotExecutableError,
)


class Store:
    def __init__(self):
        self.rows = {}
        self.lock = asyncio.Lock()
        self.status = "completed"
        self.database = self

    def get_collection(self, name):
        return self

    async def find_one_and_update(self, query, update, **kwargs):
        async with self.lock:
            self.rows.setdefault(query["_id"], copy.deepcopy(update["$setOnInsert"]))
            return copy.deepcopy(self.rows[query["_id"]])

    async def find_one(self, query):
        if "run_id" in query:
            return {"status": self.status}
        return copy.deepcopy(self.rows.get(query["_id"]))


def payload(**kwargs):
    return {
        "request_key": "stable",
        "run_id": "run_1",
        "source": "holdings",
        "symbols": ["AAPL"],
        "proposals": [],
        "research": {"AAPL": "Research"},
        **kwargs,
    }


@pytest.mark.asyncio
async def test_atomic_replay_conflict_and_cancellation_projection():
    store = Store()
    repo = DecisionAssessmentRepository(store)
    results = await asyncio.gather(
        *(repo.assess_and_persist(**payload()) for _ in range(20))
    )
    assert len(store.rows) == 1 and len({r.assessment_id for r in results}) == 1
    with pytest.raises(AssessmentConflict):
        await repo.assess_and_persist(**payload(research={"AAPL": "Changed"}))
    for state, code in [
        ("cancelled", "RUN_CANCELLED"),
        ("failed", "RUN_FAILED"),
        ("running", "RUN_IN_PROGRESS"),
        (None, "RUN_UNVERIFIED"),
    ]:
        store.status = state
        result = await repo.get(results[0].assessment_id)
        assert result.readiness == "needs_review" and not result.actionable
        assert any(r.code == code for r in result.results[0].reasons)
    assert next(iter(store.rows.values()))["readiness"] == "research_only"


@pytest.mark.asyncio
async def test_duplicate_key_race_and_empty_write_receipt():
    store = Store()
    repo = DecisionAssessmentRepository(store)
    original = await repo.assess_and_persist(**payload())
    store.find_one_and_update = AsyncMock(side_effect=DuplicateKeyError("raced"))
    replay = await repo.assess_and_persist(**payload())
    assert replay.assessment_id == original.assessment_id
    store.find_one_and_update = AsyncMock(return_value=None)
    with pytest.raises(RuntimeError, match="no record"):
        await repo.assess_and_persist(**payload())


@pytest.mark.asyncio
async def test_list_filters_and_truncation_leave_detail_intact():
    store = Store()
    repo = DecisionAssessmentRepository(store)
    saved = await repo.assess_and_persist(
        **payload(run_id=None, research={"AAPL": "x" * 1500})
    )
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.__aiter__.return_value = [copy.deepcopy(next(iter(store.rows.values())))]
    store.find = MagicMock(return_value=cursor)
    page = await repo.list(symbol="aapl", source="holdings", limit=7)
    store.find.assert_called_once_with({"results.symbol": "AAPL", "source": "holdings"})
    cursor.limit.assert_called_once_with(7)
    assert len(page[0].results[0].research) == 1000
    assert page[0].results[0].research_truncated
    detail = await repo.get(saved.assessment_id)
    assert (
        len(detail.results[0].research) == 1500
        and not detail.results[0].research_truncated
    )
    assert await repo.get("missing") is None


@pytest.mark.asyncio
async def test_store_failure_is_not_a_saved_assessment():
    collection = MagicMock()
    collection.find_one_and_update = AsyncMock(side_effect=RuntimeError("write failed"))
    with pytest.raises(RuntimeError):
        await DecisionAssessmentRepository(collection).assess_and_persist(**payload())


@pytest.mark.asyncio
async def test_watchlist_only_assesses_and_propagates_write_failure():
    repo = MagicMock()
    repo.assess = AsyncMock()
    messages = MagicMock()
    handler = OrderHandler(messages, repo)
    await handler.place_order("AAPL", "BUY", 10, "analysis1", "chat1", "local", None)
    assert repo.assess.await_args.kwargs["symbols"] == ["AAPL"]
    repo.create.assert_not_called()
    messages.update_metadata.assert_not_called()
    repo.assess.side_effect = RuntimeError("write failed")
    with pytest.raises(RuntimeError):
        await handler.place_order(
            "AAPL", "BUY", 10, "analysis1", "chat1", "local", None
        )


@pytest.mark.asyncio
async def test_legacy_mark_executed_cannot_change_account():
    repo = MagicMock()
    repo.get = AsyncMock(return_value=MagicMock(status="suggested", side="buy"))
    mongo = MagicMock()
    tx = MagicMock()
    holdings = MagicMock()
    with pytest.raises(OrderNotExecutableError):
        await mark_order_executed(
            mongodb=mongo,
            order_repo=repo,
            tx_repo=tx,
            holding_repo=holdings,
            order_id="old",
            filled_qty=10,
            filled_avg_price=100,
            executed_at=None,
            notes=None,
        )
    tx.create.assert_not_called()
    holdings.update.assert_not_called()
    mongo.get_collection.assert_not_called()
