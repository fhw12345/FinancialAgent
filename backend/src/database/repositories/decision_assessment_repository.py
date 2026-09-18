"""Atomic non-actionable batches. Legacy portfolio_orders are never promoted."""

from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from ...core.exceptions import AppError
from ...models.decision_assessment import AssessmentReason, DecisionAssessment
from ...services.decision_policy.builder import build_assessment

COLLECTION = "decision_assessments"


class AssessmentConflict(AppError):
    status_code = 409
    error_type = "assessment_conflict"


class DecisionWriteRejected(AppError):
    status_code = 409
    error_type = "decision_not_ready"

    def __init__(self) -> None:
        super().__init__(
            "Research/legacy decisions cannot authorize execution; paper review approval is separate. Record actual trades independently."
        )


class DecisionAssessmentRepository:
    def __init__(self, collection: AsyncIOMotorCollection[dict[str, Any]]) -> None:
        self.collection = collection

    async def assess_and_persist(self, **inputs: Any) -> DecisionAssessment:
        assessment = build_assessment(**inputs)
        document = assessment.model_dump()
        if assessment.portfolio_risk:
            # BSON supports datetimes, not session dates. Keep the nested versioned
            # receipt in its JSON wire form; strict model reads reconstruct dates.
            document["portfolio_risk"] = assessment.portfolio_risk.model_dump(
                mode="json"
            )
        if assessment.strategy:
            document["strategy"] = assessment.strategy.model_dump(mode="json")
        saved: dict[str, Any] | None
        try:
            saved = await self.collection.find_one_and_update(
                {"_id": assessment.assessment_id},
                {"$setOnInsert": document},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            saved = await self.collection.find_one({"_id": assessment.assessment_id})
        if saved is None:
            raise RuntimeError("Assessment persistence returned no record")
        if saved["input_hash"] != assessment.input_hash:
            raise AssessmentConflict(
                "The same assessment request key has different inputs"
            )
        saved.pop("_id", None)
        return DecisionAssessment.model_validate(saved)

    async def _project(self, doc: dict[str, Any]) -> DecisionAssessment:
        doc.pop("_id", None)
        assessment = DecisionAssessment.model_validate(doc)
        if assessment.portfolio_risk:
            from ...services.portfolio_risk.service import project_stale

            assessment.portfolio_risk = await project_stale(
                self.collection.database, assessment.portfolio_risk
            )
        if assessment.strategy:
            from ...services.research_strategy.service import project

            assessment.strategy = await project(
                self.collection.database, assessment.strategy
            )
        if not assessment.run_id:
            return assessment
        run = await self.collection.database.get_collection("agent_runs").find_one(
            {"run_id": assessment.run_id}
        )
        status = run.get("status") if run else None
        assessment.run_status = status
        if status != "completed":
            code: Literal[
                "RUN_CANCELLED", "RUN_FAILED", "RUN_IN_PROGRESS", "RUN_UNVERIFIED"
            ] = (
                "RUN_CANCELLED"
                if status == "cancelled"
                else (
                    "RUN_FAILED"
                    if status == "failed"
                    else (
                        "RUN_IN_PROGRESS"
                        if status in ("pending", "running", "waiting_for_input")
                        else "RUN_UNVERIFIED"
                    )
                )
            )
            message = "The associated run is not completed; this is a partial research artifact, never an actionable decision."
            assessment.readiness = "needs_review"
            for result in assessment.results:
                result.readiness = "needs_review"
                result.reasons.append(AssessmentReason(code=code, message=message))
        return assessment

    async def get(self, assessment_id: str) -> DecisionAssessment | None:
        doc = await self.collection.find_one({"_id": assessment_id})
        return await self._project(doc) if doc else None

    async def list(
        self, symbol: str | None = None, source: str | None = None, limit: int = 50
    ) -> list[DecisionAssessment]:
        query: dict[str, Any] = {}
        if symbol:
            query["results.symbol"] = symbol.upper()
        if source:
            query["source"] = source
        cursor = self.collection.find(query).sort("created_at", -1).limit(limit)
        results = [await self._project(doc) async for doc in cursor]
        for assessment in results:
            for result in assessment.results:
                if len(result.research) > 1000:
                    result.research = result.research[:1000]
                    result.research_truncated = True
        return results
