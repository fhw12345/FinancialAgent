from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.database.repositories.evaluation_run_repository import (
    EvaluationRunRepository,
)
from src.evals.live_schemas import (
    LiveEvaluationMetrics,
    LiveEvaluationReport,
)


def _report() -> LiveEvaluationReport:
    return LiveEvaluationReport(
        run_id="eval_live_repository",
        lane="fake_live",
        status="running",
        created_at=datetime(2026, 8, 4, 7, 0, tzinfo=UTC),
        max_cost_usd=1,
        metrics=LiveEvaluationMetrics(),
        gates_passed=False,
    )


@pytest.mark.asyncio
async def test_repository_persists_native_datetimes():
    collection = AsyncMock()
    repository = EvaluationRunRepository(collection)

    await repository.save(_report())

    document = collection.replace_one.await_args.args[1]
    assert isinstance(document["created_at"], datetime)


@pytest.mark.asyncio
async def test_repository_marks_stale_running_reports_failed():
    collection = AsyncMock()
    collection.update_many.return_value = SimpleNamespace(modified_count=2)
    repository = EvaluationRunRepository(collection)
    stale_before = datetime.now(UTC) - timedelta(hours=4)

    modified = await repository.fail_stale_running(stale_before)

    assert modified == 2
    query = collection.update_many.await_args.args[0]
    update = collection.update_many.await_args.args[1]
    assert query["created_at"] == {"$lt": stale_before}
    assert update["$set"]["status"] == "failed"
