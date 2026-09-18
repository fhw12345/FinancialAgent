"""Explicit local paper-review configuration, target proposals and human approval. No fills."""

from fastapi import APIRouter, Depends, Request

from ...database.mongodb import MongoDB
from ...models.decision_review import (
    ApproveReview,
    ConfirmReviewPolicy,
    ProposeReview,
    ReconcileReview,
    ReviewSettings,
    ReviewView,
    RevisionRequest,
)
from ...services.decision_policy import policies, review_service
from ..copilot import local_action, no_store
from ..dependencies.rate_limit import limiter
from ..dependencies.storage import get_mongodb

router = APIRouter(dependencies=[Depends(no_store)])


@router.get("/review-policy", response_model=ReviewSettings)
async def settings(db: MongoDB = Depends(get_mongodb)) -> ReviewSettings:
    return await policies.settings(db)


@router.post(
    "/review-policy",
    response_model=ReviewSettings,
    dependencies=[Depends(local_action)],
)
async def confirm(
    body: ConfirmReviewPolicy, db: MongoDB = Depends(get_mongodb)
) -> ReviewSettings:
    return await policies.confirm(db, body)


@router.post(
    "/review-policy/deactivate",
    response_model=ReviewSettings,
    dependencies=[Depends(local_action)],
)
async def deactivate(
    body: RevisionRequest, db: MongoDB = Depends(get_mongodb)
) -> ReviewSettings:
    return await policies.deactivate(db, body)


@router.post(
    "/review-control/reconcile",
    response_model=ReviewSettings,
    dependencies=[Depends(local_action)],
)
async def reconcile(
    body: ReconcileReview, db: MongoDB = Depends(get_mongodb)
) -> ReviewSettings:
    return await policies.reconcile(db, body)


@router.get("/review-batches", response_model=list[ReviewView])
async def recent(db: MongoDB = Depends(get_mongodb)) -> list[ReviewView]:
    return await review_service.recent(db)


@router.get("/review-batches/{batch_id}", response_model=ReviewView)
async def detail(batch_id: str, db: MongoDB = Depends(get_mongodb)) -> ReviewView:
    return await review_service.get(db, batch_id)


@router.post(
    "/review-batches", response_model=ReviewView, dependencies=[Depends(local_action)]
)
@limiter.limit("6/minute")
async def propose(
    request: Request, body: ProposeReview, db: MongoDB = Depends(get_mongodb)
) -> ReviewView:
    return await review_service.propose(db, body)


@router.post(
    "/review-batches/{batch_id}/approve",
    response_model=ReviewView,
    dependencies=[Depends(local_action)],
)
@limiter.limit("6/minute")
async def approve(
    request: Request,
    batch_id: str,
    body: ApproveReview,
    db: MongoDB = Depends(get_mongodb),
) -> ReviewView:
    return await review_service.approve(db, batch_id, body)


@router.post(
    "/review-batches/{batch_id}/cancel",
    response_model=ReviewView,
    dependencies=[Depends(local_action)],
)
async def cancel(
    batch_id: str, body: RevisionRequest, db: MongoDB = Depends(get_mongodb)
) -> ReviewView:
    return await review_service.cancel(db, batch_id, body)
