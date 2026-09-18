"""Explicit strategy confirmation and immutable history; reads/selection never invoke models."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, StrictBool

from ...database.mongodb import MongoDB
from ...models.portfolio_risk import Record
from ...models.research_strategy import (
    StrategyParameters,
    StrategyState,
    StrategyVersion,
)
from ...services.research_strategy import store
from ..copilot import local_action, no_store
from ..dependencies.storage import get_mongodb

router = APIRouter(dependencies=[Depends(no_store)])


class Confirmation(Record):
    expected_revision: int = Field(ge=0, strict=True)
    request_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    cost_policy_revision: int = Field(ge=1, strict=True)
    confirm: StrictBool
    parameters: StrategyParameters


class Revision(Record):
    expected_revision: int = Field(ge=0, strict=True)


@router.get("/research-strategies")
async def catalog() -> list[dict[str, object]]:
    return [
        {
            "strategy_id": "fundamental-252@1",
            "horizon": 252,
            "unit": "XNYS_sessions",
            "benchmark": "SPY_total_return@1",
            "universe": "US_USD_nonfinancial_common_equity",
            "methods": ["peer_pe_annual@1", "fcff_proxy_dcf@1"],
            "requires_explicit_confirmation": True,
        },
        {
            "strategy_id": "short-term-experimental@1",
            "enabled": False,
            "required": [
                "signal_rules",
                "entry_session",
                "exit_rules",
                "event_exclusions",
                "costs",
                "independent_horizon_benchmark",
            ],
            "reason": "Pilot not authorized",
        },
    ]


@router.get("/research-strategy", response_model=StrategyState)
async def state(db: MongoDB = Depends(get_mongodb)) -> StrategyState:
    return await store.state(db)


@router.post(
    "/research-strategy",
    response_model=StrategyState,
    dependencies=[Depends(local_action)],
)
async def confirm(
    body: Confirmation, db: MongoDB = Depends(get_mongodb)
) -> StrategyState:
    if not body.confirm:
        raise HTTPException(422, "Explicit strategy confirmation is required")
    return await store.confirm(
        db,
        body.parameters,
        body.expected_revision,
        body.request_id,
        body.cost_policy_revision,
    )


@router.post(
    "/research-strategy/deactivate",
    response_model=StrategyState,
    dependencies=[Depends(local_action)],
)
async def deactivate(
    body: Revision, db: MongoDB = Depends(get_mongodb)
) -> StrategyState:
    return await store.deactivate(db, body.expected_revision)


@router.get("/research-strategy/runs/{run_id}")
async def run_strategy(
    run_id: str, db: MongoDB = Depends(get_mongodb)
) -> dict[str, object] | None:
    from ...models.research_strategy import StrategySummary
    from ...services.research_strategy.service import project

    row = await db.get_collection("decision_assessments").find_one({"run_id": run_id})
    if not row or not row.get("strategy"):
        return None
    return (
        await project(db, StrategySummary.model_validate(row["strategy"]))
    ).model_dump(mode="json")


@router.get("/research-strategies/{version_id}", response_model=StrategyVersion)
async def version(
    version_id: str, db: MongoDB = Depends(get_mongodb)
) -> StrategyVersion:
    versions = (await store.state(db)).versions
    found = next((v for v in versions if v.version_id == version_id), None)
    if found is None:
        raise HTTPException(404, "Strategy version not found")
    return found
