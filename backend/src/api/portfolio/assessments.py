"""Stage-A read API and explicit rejection of approval attempts."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from ...database.mongodb import MongoDB
from ...database.repositories.decision_assessment_repository import (
    COLLECTION,
    DecisionAssessmentRepository,
    DecisionWriteRejected,
)
from ...models.decision_assessment import DecisionAssessment
from ..dependencies.rate_limit import limiter
from ..dependencies.storage import get_mongodb

router = APIRouter()


def get_assessments(
    mongodb: MongoDB = Depends(get_mongodb),
) -> DecisionAssessmentRepository:
    return DecisionAssessmentRepository(mongodb.get_collection(COLLECTION))


@router.get("/decision-policy")
async def decision_policy() -> dict[str, object]:
    return {
        "phase": "A",
        "actionable": False,
        "approval_enabled": False,
        "risk_preview_available": True,
        "research_strategy_contracts_available": True,
        "pending": [
            "confirmed_policy",
            "review_approval",
            "point_in_time_evidence",
            "strategy_contract",
        ],
    }


@router.get("/assessments", response_model=list[DecisionAssessment])
@limiter.limit("60/minute")
async def list_assessments(
    request: Request,
    response: Response,
    symbol: str | None = None,
    source: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    repository: DecisionAssessmentRepository = Depends(get_assessments),
) -> list[DecisionAssessment]:
    response.headers["Cache-Control"] = "no-store"
    return await repository.list(symbol, source, limit)


@router.get("/assessments/{assessment_id}", response_model=DecisionAssessment)
async def get_assessment(
    assessment_id: str,
    response: Response,
    repository: DecisionAssessmentRepository = Depends(get_assessments),
) -> DecisionAssessment:
    response.headers["Cache-Control"] = "no-store"
    result = await repository.get(assessment_id)
    if result is None:
        raise HTTPException(404, "Assessment not found")
    return result


@router.post("/assessments/{assessment_id}/approve")
@router.post("/decisions/{assessment_id}/approve")
async def reject_approval(assessment_id: str) -> None:
    # Stage A has no approval implementation or override, including for legacy IDs.
    raise DecisionWriteRejected()
