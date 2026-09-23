"""Explicit model-decision requests. Recommendations only; approval stays in review-batches."""

from fastapi import APIRouter, Depends, Request

from ...database.mongodb import MongoDB
from ...models.decision_review import RevisionRequest
from ...services.decision_policy import model_decision, model_review
from ...services.decision_policy.model_decision import (
    ModelDecisionView,
    RequestModelDecision,
)
from ..copilot import local_action, no_store
from ..dependencies.rate_limit import limiter
from ..dependencies.storage import get_mongodb

router = APIRouter(dependencies=[Depends(no_store)])


@router.post(
    "/model-decisions",
    response_model=ModelDecisionView,
    dependencies=[Depends(local_action)],
)
@limiter.limit("3/minute")
async def request_decision(
    request: Request, body: RequestModelDecision, db: MongoDB = Depends(get_mongodb)
) -> ModelDecisionView:
    agent = getattr(request.app.state, "portfolio_agent", None)
    return await model_decision.decide(db, agent, body)


@router.get("/model-decisions", response_model=list[ModelDecisionView])
async def recent(db: MongoDB = Depends(get_mongodb)) -> list[ModelDecisionView]:
    return [
        await model_review.view(db, r.decision_id)
        for r in await model_decision.recent(db)
    ]


@router.get("/model-decisions/{decision_id}", response_model=ModelDecisionView)
async def detail(
    decision_id: str, db: MongoDB = Depends(get_mongodb)
) -> ModelDecisionView:
    return await model_review.view(db, decision_id)


@router.post(
    "/model-decisions/{decision_id}/review",
    response_model=ModelDecisionView,
    dependencies=[Depends(local_action)],
)
@limiter.limit("6/minute")
async def revalidate(
    request: Request,
    decision_id: str,
    body: RevisionRequest,
    db: MongoDB = Depends(get_mongodb),
) -> ModelDecisionView:
    return await model_review.revalidate(db, decision_id, body)
