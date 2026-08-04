from __future__ import annotations

from datetime import datetime
from typing import Any

from src.evals.live_schemas import (
    EvaluationRunSummary,
    LiveEvaluationReport,
)

EVALUATION_RUNS_COLLECTION = "evaluation_runs"


class EvaluationRunRepository:
    def __init__(self, collection: Any) -> None:
        self.collection = collection

    async def ensure_indexes(self) -> None:
        await self.collection.create_index("run_id", unique=True, name="run_id_1")
        await self.collection.create_index(
            [("created_at", -1)],
            name="created_at_-1",
        )
        await self.collection.create_index(
            [("lane", 1), ("created_at", -1)],
            name="lane_1_created_at_-1",
        )

    async def save(self, report: LiveEvaluationReport) -> None:
        await self.collection.replace_one(
            {"run_id": report.run_id},
            report.model_dump(mode="python"),
            upsert=True,
        )

    async def fail_stale_running(self, stale_before: datetime) -> int:
        result = await self.collection.update_many(
            {
                "status": "running",
                "created_at": {"$lt": stale_before},
            },
            {
                "$set": {
                    "status": "failed",
                    "completed_at": datetime.now(stale_before.tzinfo),
                    "gates_passed": False,
                    "error": "Evaluation worker stopped before completion",
                }
            },
        )
        return int(result.modified_count)

    async def get(self, run_id: str) -> LiveEvaluationReport | None:
        document = await self.collection.find_one({"run_id": run_id}, {"_id": 0})
        return LiveEvaluationReport.model_validate(document) if document else None

    async def list(self, limit: int = 20) -> list[EvaluationRunSummary]:
        cursor = (
            self.collection.find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
        )
        summaries: list[EvaluationRunSummary] = []
        async for document in cursor:
            metrics = document.get("metrics") or {}
            summaries.append(
                EvaluationRunSummary(
                    run_id=document["run_id"],
                    suite_version=document.get("suite_version", "unknown"),
                    lane=document.get("lane", "unknown"),
                    status=document.get("status", "unknown"),
                    created_at=document["created_at"],
                    completed_at=document.get("completed_at"),
                    gates_passed=bool(document.get("gates_passed", False)),
                    case_pass_rate=float(metrics.get("case_pass_rate", 0.0)),
                    estimated_cost_usd=float(metrics.get("estimated_cost_usd", 0.0)),
                )
            )
        return summaries
