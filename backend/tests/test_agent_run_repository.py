"""Tests for the shared durable AgentRun state machine."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.utils.date_utils import utcnow
from src.database.repositories.agent_run_repository import AgentRunRepository
from src.models.agent_run import AgentRun
from src.services.agent_run_service import AgentRunService


class FakeCursor:
    def __init__(self, documents: list[dict]) -> None:
        self.documents = documents

    def sort(self, field, direction=None):
        fields = field if isinstance(field, list) else [(field, direction)]
        for sort_field, sort_direction in reversed(fields):
            self.documents.sort(
                key=lambda document: document.get(sort_field),
                reverse=sort_direction < 0,
            )
        return self

    def limit(self, limit: int):
        self.documents = self.documents[:limit]
        return self

    def __aiter__(self):
        async def iterate():
            for document in self.documents:
                yield deepcopy(document)

        return iterate()


class FakeRunCollection:
    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}
        self.sequence = 0
        self.create_index = AsyncMock()
        self.update_many = AsyncMock(return_value=SimpleNamespace(modified_count=0))

    async def insert_one(self, document: dict):
        self.sequence += 1
        self.documents[document["run_id"]] = {
            **deepcopy(document),
            "_id": self.sequence,
        }
        return SimpleNamespace(inserted_id=document["run_id"])

    async def find_one(self, query: dict, sort=None):
        matches = [
            document
            for document in self.documents.values()
            if self._matches(document, query)
        ]
        if sort:
            field, direction = sort[0]
            matches.sort(
                key=lambda document: document.get(field),
                reverse=direction < 0,
            )
        return deepcopy(matches[0]) if matches else None

    async def find_one_and_update(
        self,
        query: dict,
        update: dict,
        return_document=None,
    ):
        for run_id, document in self.documents.items():
            if self._matches(document, query):
                self.documents[run_id] = {
                    **document,
                    **deepcopy(update["$set"]),
                }
                for key in update.get("$unset", {}):
                    self.documents[run_id].pop(key, None)
                return deepcopy(self.documents[run_id])
        return None

    def find(self, query: dict):
        return FakeCursor(
            [
                deepcopy(document)
                for document in self.documents.values()
                if self._matches(document, query)
            ]
        )

    @staticmethod
    def _matches(document: dict, query: dict) -> bool:
        for key, expected in query.items():
            actual = document.get(key)
            if isinstance(expected, dict) and "$in" in expected:
                if actual not in expected["$in"]:
                    return False
            elif actual != expected:
                return False
        return True


def make_run(run_id: str = "run_1", **updates) -> AgentRun:
    payload = {
        "run_id": run_id,
        "requested_policy": "auto",
        "policy_version": "auto-router-v1",
        "status": "pending",
        "started_at": utcnow(),
    }
    payload.update(updates)
    return AgentRun(**payload)


@pytest.mark.asyncio
async def test_atomic_state_transitions_make_terminal_status_immutable():
    repository = AgentRunRepository(FakeRunCollection())  # type: ignore[arg-type]
    await repository.create(make_run())

    running = await repository.transition(
        "run_1",
        from_statuses=("pending",),
        to_status="running",
        execution_mode="agentic",
    )
    completed = await repository.transition(
        "run_1",
        from_statuses=("running",),
        to_status="completed",
        finished_at=utcnow(),
    )
    overwritten = await repository.transition(
        "run_1",
        from_statuses=("completed",),
        to_status="cancelled",
    )

    assert running is not None
    assert running.execution_mode == "agentic"
    assert completed is not None
    assert completed.status == "completed"
    assert overwritten is None
    assert (await repository.get("run_1")).status == "completed"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_lists_chat_runs_and_finds_active_portfolio_key():
    collection = FakeRunCollection()
    repository = AgentRunRepository(collection)  # type: ignore[arg-type]
    await repository.create(make_run("run_old", chat_id="chat_1"))
    await repository.create(
        make_run(
            "run_new",
            chat_id="chat_1",
            portfolio_key="holdings",
            status="running",
            started_at=utcnow(),
        )
    )

    runs = await repository.list_by_chat("chat_1")
    active = await repository.get_active_by_portfolio_key("holdings")

    assert [run.run_id for run in runs] == ["run_new", "run_old"]
    assert active is not None
    assert active.run_id == "run_new"


@pytest.mark.asyncio
async def test_service_records_policy_models_and_metrics():
    repository = AgentRunRepository(FakeRunCollection())  # type: ignore[arg-type]
    service = AgentRunService(repository)

    with patch(
        "src.services.agent_run_service.get_role_models",
        return_value={
            "react_agent": "model-react",
            "simple_chat": "model-simple",
            "deep_planner": "model-deep",
            "sub_technical": "model-tech",
            "sub_news": "model-news",
            "sub_financial": "model-financial",
            "sub_debater": "model-debater",
            "verdict": "model-verdict",
            "portfolio_research": "model-research",
            "portfolio_decisions": "model-decisions",
        },
    ):
        created = await service.create_chat_run(requested_policy="auto")
        running = await service.mark_running(
            created.run_id,
            selected_policy="v3",
            chat_id="chat_1",
        )
        completed = await service.complete(
            created.run_id,
            tool_calls=2,
            input_tokens=100,
            output_tokens=50,
        )

    assert running is not None
    assert running.execution_mode == "agentic"
    assert running.model_routes == {"react_agent": "model-react"}
    assert running.prompt_versions == {"react_agent": "react-agent-v1"}
    assert completed is not None
    assert completed.status == "completed"
    assert completed.tool_calls == 2
    assert completed.input_tokens == 100
    assert completed.output_tokens == 50


@pytest.mark.asyncio
async def test_portfolio_service_claims_one_active_key_with_lease():
    repository = AsyncMock()
    existing = make_run(
        "run_existing",
        portfolio_key="holdings",
        active_portfolio_key="holdings",
        execution_mode="portfolio",
    )
    repository.claim_portfolio_run.return_value = (existing, False)
    service = AgentRunService(repository)

    with patch(
        "src.services.agent_run_service.get_role_models",
        return_value={
            "portfolio_research": "model-research",
            "portfolio_decisions": "model-decisions",
        },
    ):
        claimed, created = await service.create_portfolio_run(portfolio_key="holdings")

    repository.release_stale_portfolio_claim.assert_awaited_once()
    candidate = repository.claim_portfolio_run.await_args.args[0]
    assert candidate.active_portfolio_key == "holdings"
    assert candidate.lease_expires_at is not None
    assert claimed.run_id == "run_existing"
    assert created is False


@pytest.mark.asyncio
async def test_ensure_indexes_creates_shared_lookup_indexes():
    collection = MagicMock()
    collection.create_index = AsyncMock()
    repository = AgentRunRepository(collection)

    await repository.ensure_indexes()

    names = {call.kwargs["name"] for call in collection.create_index.await_args_list}
    assert names == {
        "run_id_1",
        "chat_id_1_started_at_-1",
        "portfolio_key_1_started_at_-1",
        "active_portfolio_key_1",
        "status_1_started_at_-1",
    }
