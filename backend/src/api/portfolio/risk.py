"""Versioned risk reads/refresh and explicit preview-policy confirmation. No approval."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, StrictBool

from ...database.mongodb import MongoDB
from ...models.portfolio_risk import (
    PolicyState,
    PortfolioRiskReview,
    Record,
    RiskPolicy,
)
from ...services.portfolio_risk import service
from ..copilot import local_action, no_store
from ..dependencies.rate_limit import limiter
from ..dependencies.storage import get_mongodb

router = APIRouter(dependencies=[Depends(no_store)])


class PolicyConfirmation(Record):
    expected_revision: int = Field(ge=0, strict=True)
    confirm: StrictBool
    policy: RiskPolicy


@router.get("/risk", response_model=PortfolioRiskReview | None)
async def get_risk(mongo: MongoDB = Depends(get_mongodb)) -> PortfolioRiskReview | None:
    return await service.latest(mongo)


@router.post(
    "/risk/refresh",
    response_model=PortfolioRiskReview,
    dependencies=[Depends(local_action)],
)
@limiter.limit("6/minute")
async def refresh_risk(
    request: Request, mongo: MongoDB = Depends(get_mongodb)
) -> PortfolioRiskReview:
    return await service.review_current(mongo)


@router.get("/risk-policy", response_model=PolicyState)
async def get_policy(mongo: MongoDB = Depends(get_mongodb)) -> PolicyState:
    return await service.policy_state(mongo)


@router.put(
    "/risk-policy", response_model=PolicyState, dependencies=[Depends(local_action)]
)
async def put_policy(
    body: PolicyConfirmation, mongo: MongoDB = Depends(get_mongodb)
) -> PolicyState:
    if not body.confirm:
        raise HTTPException(
            422, "Explicit confirmation required; no personal limits are inferred"
        )
    return await service.confirm_policy(mongo, body.policy, body.expected_revision)
