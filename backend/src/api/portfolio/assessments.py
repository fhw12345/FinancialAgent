"""Immutable research read API. Approval belongs only to separately validated review batches."""

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
        "phase": "B",
        "actionable": False,
        "approval_enabled": False,
        "risk_preview_available": True,
        "research_strategy_contracts_available": True,
        "paper_review_approval_available": True,
        "paper_review_endpoint": "/api/portfolio/review-batches",
        "execution_available": False,
        "pending": ["user_confirmed_policy_and_targets", "validated_review_batch"],
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
    # Research/legacy IDs are never approval authority. Only review-batches can be approved.
    raise DecisionWriteRejected()
