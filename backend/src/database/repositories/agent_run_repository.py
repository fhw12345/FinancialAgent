"""MongoDB repository for shared durable agent runs."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from ...models.agent_run import (
    ALLOWED_RUN_TRANSITIONS,
    AgentRun,
    AgentRunStatus,
)

AGENT_RUNS_COLLECTION = "agent_runs"


class AgentRunRepository:
    """Persist and atomically transition shared agent runs."""

    def __init__(self, collection: Any) -> None:
        self.collection = collection

    async def ensure_indexes(self) -> None:
        await self.collection.create_index("run_id", unique=True, name="run_id_1")
        await self.collection.create_index(
            "request_id",
            unique=True,
            partialFilterExpression={"request_id": {"$type": "string"}},
            name="request_id_1",
        )
        await self.collection.create_index(
            [("chat_id", 1), ("started_at", -1)],
            name="chat_id_1_started_at_-1",
        )
        await self.collection.create_index(
            [("portfolio_key", 1), ("started_at", -1)],
            name="portfolio_key_1_started_at_-1",
        )
        await self.collection.create_index(
            "active_portfolio_key",
            unique=True,
            partialFilterExpression={"active_portfolio_key": {"$type": "string"}},
            name="active_portfolio_key_1",
        )
        await self.collection.create_index(
            [("status", 1), ("started_at", -1)],
            name="status_1_started_at_-1",
        )

    async def create(self, run: AgentRun) -> AgentRun:
        await self.collection.insert_one(run.model_dump(exclude_none=True))
        return run

    async def claim_request_run(self, run: AgentRun) -> tuple[AgentRun, bool]:
        if run.request_id is None:
            return await self.create(run), True
        try:
            await self.collection.insert_one(run.model_dump(exclude_none=True))
            return run, True
        except DuplicateKeyError:
            existing = await self.get_by_request_id(run.request_id)
            if existing is None:
                raise
            return existing, False

    async def claim_portfolio_run(self, run: AgentRun) -> tuple[AgentRun, bool]:
        """Insert one active run per portfolio key, returning the winner."""
        for _ in range(2):
            try:
                await self.collection.insert_one(run.model_dump(exclude_none=True))
                return run, True
            except DuplicateKeyError:
                existing = await self.get_active_by_portfolio_key(
                    run.portfolio_key or ""
                )
                if existing is not None:
                    return existing, False
        await self.collection.insert_one(run.model_dump(exclude_none=True))
        return run, True

    async def get(self, run_id: str) -> AgentRun | None:
        document = await self.collection.find_one({"run_id": run_id})
        return self._parse(document)

    async def get_by_request_id(self, request_id: str) -> AgentRun | None:
        document = await self.collection.find_one({"request_id": request_id})
        return self._parse(document)

    async def list_by_chat(
        self,
        chat_id: str,
        *,
        limit: int = 20,
    ) -> list[AgentRun]:
        cursor = (
            self.collection.find({"chat_id": chat_id})
            .sort([("started_at", -1), ("_id", -1)])
            .limit(limit)
        )
        runs: list[AgentRun] = []
        async for document in cursor:
            parsed = self._parse(document)
            if parsed is not None:
                runs.append(parsed)
        return runs

    async def get_latest_by_portfolio_key(
        self,
        portfolio_key: str,
    ) -> AgentRun | None:
        document = await self.collection.find_one(
            {"portfolio_key": portfolio_key},
            sort=[("started_at", -1), ("_id", -1)],
        )
        return self._parse(document)

    async def get_active_by_portfolio_key(
        self,
        portfolio_key: str,
    ) -> AgentRun | None:
        document = await self.collection.find_one(
            {
                "portfolio_key": portfolio_key,
                "status": {"$in": ["pending", "running"]},
            },
            sort=[("started_at", -1), ("_id", -1)],
        )
        return self._parse(document)

    async def release_stale_portfolio_claim(
        self,
        portfolio_key: str,
        *,
        now: datetime,
    ) -> int:
        result = await self.collection.update_many(
            {
                "active_portfolio_key": portfolio_key,
                "status": {"$in": ["pending", "running"]},
                "lease_expires_at": {"$lte": now},
            },
            {
                "$set": {
                    "status": "failed",
                    "finished_at": now,
                    "error_code": "STALE_RUN_LEASE",
                    "error_message": "Run lease expired before completion",
                },
                "$unset": {"active_portfolio_key": ""},
            },
        )
        return int(result.modified_count)

    async def update_fields(
        self,
        run_id: str,
        **fields: Any,
    ) -> AgentRun | None:
        updates = {key: value for key, value in fields.items() if value is not None}
        if not updates:
            return await self.get(run_id)
        document = await self.collection.find_one_and_update(
            {"run_id": run_id},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        return self._parse(document)

    async def merge_prompt_versions(
        self,
        run_id: str,
        prompt_versions: dict[str, str],
    ) -> AgentRun | None:
        if not prompt_versions:
            return await self.get(run_id)
        document = await self.collection.find_one_and_update(
            {"run_id": run_id},
            {
                "$set": {
                    f"prompt_versions.{prompt_id}": version
                    for prompt_id, version in prompt_versions.items()
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._parse(document)

    async def transition(
        self,
        run_id: str,
        *,
        from_statuses: Iterable[AgentRunStatus],
        to_status: AgentRunStatus,
        **fields: Any,
    ) -> AgentRun | None:
        allowed_from = [
            status
            for status in from_statuses
            if to_status in ALLOWED_RUN_TRANSITIONS[status]
        ]
        if not allowed_from:
            return None
        updates = {
            "status": to_status,
            **{key: value for key, value in fields.items() if value is not None},
        }
        update: dict[str, Any] = {"$set": updates}
        if to_status in {"completed", "failed", "cancelled"}:
            update["$unset"] = {"active_portfolio_key": ""}
        document = await self.collection.find_one_and_update(
            {
                "run_id": run_id,
                "status": {"$in": allowed_from},
            },
            update,
            return_document=ReturnDocument.AFTER,
        )
        return self._parse(document)

    @staticmethod
    def _parse(document: dict[str, Any] | None) -> AgentRun | None:
        if document is None:
            return None
        document.pop("_id", None)
        return AgentRun(**document)
