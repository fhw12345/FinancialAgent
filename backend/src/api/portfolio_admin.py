"""
Portfolio analysis admin endpoints:
- GET/PUT /api/admin/portfolio/settings  — user-set cash + risk + max position
- POST    /api/admin/portfolio/trigger-analysis?flow=holdings|picks
- GET     /api/admin/portfolio/status/{run_id}
- GET     /api/admin/portfolio/universe/sectors

Background tasks live in-process via FastAPI BackgroundTasks. Per-button
idempotency: re-trigger of the same flow while it's running returns the
existing run doc (no second task spawned).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, ValidationError

from ..data.sector_universe import list_sectors
from ..database.mongodb import MongoDB
from ..models.portfolio_analysis import (
    AnalysisRun,
    PortfolioSettings,
    PortfolioSettingsUpdate,
)
from .dependencies.auth import get_mongodb
from .dependencies.rate_limit import limiter

logger = structlog.get_logger()

router = APIRouter(prefix="/api/admin/portfolio", tags=["portfolio-admin"])


# ---------- Settings ----------


@router.get("/settings", response_model=PortfolioSettings | None)
@limiter.limit("60/minute")
async def get_settings(
    request: Request, mongodb: MongoDB = Depends(get_mongodb)
) -> PortfolioSettings | None:
    doc = await mongodb.get_collection("user_settings").find_one({})
    if not doc:
        return None
    doc.pop("_id", None)
    try:
        return PortfolioSettings(**doc)
    except ValidationError:
        # Stored doc is partial / invalid — surface as "unset" so frontend
        # disables buttons until user resaves.
        logger.warning("user_settings_invalid_in_db", doc=doc)
        return None


@router.put("/settings", response_model=PortfolioSettings)
@limiter.limit("60/minute")
async def put_settings(
    request: Request,
    payload: PortfolioSettingsUpdate,
    mongodb: MongoDB = Depends(get_mongodb),
) -> PortfolioSettings:
    # Strict: all fields required at PUT (PRD: ALL REQUIRED, no defaults).
    if (
        payload.cash_balance is None
        or payload.risk_tolerance is None
        or payload.max_position_pct is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="cash_balance, risk_tolerance, max_position_pct are all required",
        )
    try:
        validated = PortfolioSettings(
            cash_balance=payload.cash_balance,
            risk_tolerance=payload.risk_tolerance,
            max_position_pct=payload.max_position_pct,
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.errors()
        ) from e
    await mongodb.get_collection("user_settings").replace_one(
        {}, validated.model_dump(), upsert=True
    )
    return validated


# ---------- Universe sectors ----------


@router.get("/universe/sectors")
@limiter.limit("60/minute")
async def get_universe_sectors(request: Request) -> dict[str, Any]:
    """Return {sectors: [...], industries_by_sector: {sector: [industry,...]}}."""
    by_sector = list_sectors()
    return {
        "sectors": list(by_sector.keys()),
        "industries_by_sector": by_sector,
    }


# ---------- Trigger + status ----------


class TriggerRequest(BaseModel):
    sectors: list[str] | None = None  # required for flow=picks


async def _set_run(mongodb: MongoDB, run: AnalysisRun) -> None:
    await mongodb.get_collection("analysis_runs").replace_one(
        {"run_id": run.run_id}, run.model_dump(), upsert=True
    )


async def _get_run(mongodb: MongoDB, run_id: str) -> AnalysisRun | None:
    doc = await mongodb.get_collection("analysis_runs").find_one({"run_id": run_id})
    if not doc:
        return None
    doc.pop("_id", None)
    try:
        return AnalysisRun(**doc)
    except ValidationError:
        return None


async def _run_holdings_flow(
    mongodb: MongoDB, app: Any, settings: PortfolioSettings
) -> None:
    from ..agent.portfolio.flows import run_analyze_holdings

    run_id = "holdings"
    started = datetime.now(UTC)
    await _set_run(
        mongodb,
        AnalysisRun(run_id=run_id, status="running", started_at=started),
    )
    try:
        result = await run_analyze_holdings(app, settings)
        await _set_run(
            mongodb,
            AnalysisRun(
                run_id=run_id,
                status="done",
                started_at=started,
                finished_at=datetime.now(UTC),
                message=result.get("message"),
                result_count=result.get("result_count"),
            ),
        )
    except Exception as e:
        logger.error("holdings_flow_failed", error=str(e))
        await _set_run(
            mongodb,
            AnalysisRun(
                run_id=run_id,
                status="error",
                started_at=started,
                finished_at=datetime.now(UTC),
                message=f"{type(e).__name__}: {str(e)[:200]}",
            ),
        )


async def _run_picks_flow(
    mongodb: MongoDB, app: Any, settings: PortfolioSettings, sectors: list[str]
) -> None:
    from ..agent.portfolio.flows import run_today_picks

    run_id = "picks"
    started = datetime.now(UTC)
    await _set_run(
        mongodb,
        AnalysisRun(
            run_id=run_id, status="running", started_at=started, sectors=sectors
        ),
    )
    try:
        result = await run_today_picks(app, settings, sectors)
        await _set_run(
            mongodb,
            AnalysisRun(
                run_id=run_id,
                status="done",
                started_at=started,
                finished_at=datetime.now(UTC),
                message=result.get("message"),
                result_count=result.get("result_count"),
                sectors=sectors,
            ),
        )
    except Exception as e:
        logger.error("picks_flow_failed", error=str(e))
        await _set_run(
            mongodb,
            AnalysisRun(
                run_id=run_id,
                status="error",
                started_at=started,
                finished_at=datetime.now(UTC),
                message=f"{type(e).__name__}: {str(e)[:200]}",
                sectors=sectors,
            ),
        )


async def _run_single_symbol_flow(
    mongodb: MongoDB,
    app: Any,
    settings: PortfolioSettings,
    symbol: str,
    run_key: str,
) -> None:
    """W2.1+W2.2 background runner for the unified single-symbol flow."""
    from ..agent.portfolio.flows import run_single_symbol

    started = datetime.now(UTC)
    await _set_run(
        mongodb,
        AnalysisRun(run_id=run_key, status="running", started_at=started),
    )
    try:
        result = await run_single_symbol(app, symbol, settings)
        await _set_run(
            mongodb,
            AnalysisRun(
                run_id=run_key,
                status="done",
                started_at=started,
                finished_at=datetime.now(UTC),
                message=result.get("message"),
                result_count=result.get("result_count"),
            ),
        )
    except Exception as e:
        logger.error("single_symbol_flow_failed", symbol=symbol, error=str(e))
        await _set_run(
            mongodb,
            AnalysisRun(
                run_id=run_key,
                status="error",
                started_at=started,
                finished_at=datetime.now(UTC),
                message=f"{type(e).__name__}: {str(e)[:200]}",
            ),
        )


@router.post("/trigger-analysis", response_model=AnalysisRun)
@limiter.limit("30/minute")
async def trigger_analysis(
    request: Request,
    background_tasks: BackgroundTasks,
    flow: str,  # query param: 'holdings' | 'picks' | 'single_symbol'
    symbol: str | None = None,  # required when flow='single_symbol'
    payload: TriggerRequest | None = None,
    mongodb: MongoDB = Depends(get_mongodb),
) -> AnalysisRun:
    if flow not in ("holdings", "picks", "single_symbol"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="flow must be 'holdings', 'picks', or 'single_symbol'",
        )
    if flow == "single_symbol":
        if not symbol or not symbol.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="single_symbol flow requires ?symbol=TICKER",
            )

    # Idempotency: per-flow run id (single_symbol gets a per-symbol id so two
    # different symbols can run concurrently)
    run_key = f"single_{symbol.strip().upper()}" if flow == "single_symbol" else flow
    existing = await _get_run(mongodb, run_key)
    if existing and existing.status == "running":
        return existing

    # Settings must be saved
    settings_doc = await mongodb.get_collection("user_settings").find_one({})
    if not settings_doc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Save portfolio settings (cash, risk, max position) before triggering analysis",
        )
    settings_doc.pop("_id", None)
    try:
        settings = PortfolioSettings(**settings_doc)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Settings invalid: {e}",
        ) from e

    if flow == "picks":
        sectors = (payload.sectors if payload else None) or []
        background_tasks.add_task(
            _run_picks_flow, mongodb, request.app, settings, sectors
        )
    elif flow == "single_symbol":
        background_tasks.add_task(
            _run_single_symbol_flow,
            mongodb,
            request.app,
            settings,
            symbol.strip().upper(),
            run_key,
        )
    else:
        background_tasks.add_task(_run_holdings_flow, mongodb, request.app, settings)

    started = datetime.now(UTC)
    run = AnalysisRun(
        run_id=run_key,  # type: ignore[arg-type]
        status="pending",
        started_at=started,
        sectors=(payload.sectors if (flow == "picks" and payload) else None),
    )
    await _set_run(mongodb, run)
    return run


@router.get("/status/{run_id}", response_model=AnalysisRun)
@limiter.limit("120/minute")
async def get_status(
    request: Request, run_id: str, mongodb: MongoDB = Depends(get_mongodb)
) -> AnalysisRun:
    if run_id not in ("holdings", "picks") and not run_id.startswith("single_"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="run_id must be 'holdings', 'picks', or 'single_<TICKER>'",
        )
    run = await _get_run(mongodb, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No run for {run_id}",
        )
    return run
