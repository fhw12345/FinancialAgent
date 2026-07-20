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

from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, ValidationError

from ..core.utils.date_utils import utcnow
from ..data.sector_universe import list_sectors
from ..database.mongodb import MongoDB
from ..database.repositories.agent_run_repository import AgentRunRepository
from ..models.agent_run import AgentRun
from ..models.portfolio_analysis import (
    AnalysisRun,
    PortfolioSettings,
    PortfolioSettingsUpdate,
)
from ..services.agent_run_service import PORTFOLIO_RUN_LEASE, AgentRunService
from .dependencies.rate_limit import limiter
from .dependencies.run_deps import (
    get_agent_run_repository,
    get_agent_run_service,
)
from .dependencies.storage import get_mongodb

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


async def _get_legacy_run(mongodb: MongoDB, run_id: str) -> AnalysisRun | None:
    collection = mongodb.get_collection("analysis_runs")
    now = utcnow()
    await collection.update_one(
        {
            "run_id": run_id,
            "status": "running",
            "started_at": {"$lte": now - PORTFOLIO_RUN_LEASE},
        },
        {
            "$set": {
                "status": "error",
                "finished_at": now,
                "message": "Legacy run lease expired before completion",
            }
        },
    )
    doc = await collection.find_one({"run_id": run_id})
    if not doc:
        return None
    doc.pop("_id", None)
    try:
        return AnalysisRun(**doc)
    except ValidationError:
        return None


def _to_analysis_run(run: AgentRun) -> AnalysisRun:
    status_map = {
        "pending": "pending",
        "running": "running",
        "waiting_for_input": "running",
        "completed": "done",
        "failed": "error",
        "cancelled": "error",
    }
    return AnalysisRun(
        run_id=run.portfolio_key or run.run_id,
        agent_run_id=run.run_id,
        status=status_map[run.status],
        started_at=run.started_at,
        finished_at=run.finished_at,
        message=run.metadata.get("message") or run.error_message,
        result_count=run.metadata.get("result_count"),
        sectors=run.metadata.get("sectors"),
    )


async def _run_holdings_flow(
    run_service: AgentRunService,
    run_id: str,
    app: Any,
    settings: PortfolioSettings,
) -> None:
    from ..agent.portfolio.flows import run_analyze_holdings

    try:
        running = await run_service.transition_portfolio(
            run_id,
            status="running",
        )
        if running is None:
            raise RuntimeError("Could not transition holdings run to running")
        result = await run_analyze_holdings(app, settings)
        await run_service.transition_portfolio(
            run_id,
            status="completed",
            metadata={
                "message": result.get("message"),
                "result_count": result.get("result_count"),
            },
        )
    except Exception as e:
        logger.error("holdings_flow_failed", error=str(e))
        await run_service.transition_portfolio(
            run_id,
            status="failed",
            error_code="HOLDINGS_FLOW_ERROR",
            error_message=f"{type(e).__name__}: {str(e)[:200]}",
        )


async def _run_picks_flow(
    run_service: AgentRunService,
    run_id: str,
    app: Any,
    settings: PortfolioSettings,
    sectors: list[str],
) -> None:
    from ..agent.portfolio.flows import run_today_picks

    try:
        running = await run_service.transition_portfolio(
            run_id,
            status="running",
        )
        if running is None:
            raise RuntimeError("Could not transition picks run to running")
        result = await run_today_picks(app, settings, sectors)
        await run_service.transition_portfolio(
            run_id,
            status="completed",
            metadata={
                "message": result.get("message"),
                "result_count": result.get("result_count"),
                "sectors": sectors,
            },
        )
    except Exception as e:
        logger.error("picks_flow_failed", error=str(e))
        await run_service.transition_portfolio(
            run_id,
            status="failed",
            error_code="PICKS_FLOW_ERROR",
            error_message=f"{type(e).__name__}: {str(e)[:200]}",
            metadata={"sectors": sectors},
        )


async def _run_single_symbol_flow(
    run_service: AgentRunService,
    run_id: str,
    app: Any,
    settings: PortfolioSettings,
    symbol: str,
) -> None:
    """W2.1+W2.2 background runner for the unified single-symbol flow."""
    from ..agent.portfolio.flows import run_single_symbol

    try:
        running = await run_service.transition_portfolio(
            run_id,
            status="running",
        )
        if running is None:
            raise RuntimeError("Could not transition symbol run to running")
        result = await run_single_symbol(app, symbol, settings)
        await run_service.transition_portfolio(
            run_id,
            status="completed",
            metadata={
                "message": result.get("message"),
                "result_count": result.get("result_count"),
            },
        )
    except Exception as e:
        logger.error("single_symbol_flow_failed", symbol=symbol, error=str(e))
        await run_service.transition_portfolio(
            run_id,
            status="failed",
            error_code="SINGLE_SYMBOL_FLOW_ERROR",
            error_message=f"{type(e).__name__}: {str(e)[:200]}",
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
    run_repository: AgentRunRepository = Depends(get_agent_run_repository),
    run_service: AgentRunService = Depends(get_agent_run_service),
) -> AnalysisRun:
    if flow not in ("holdings", "picks", "single_symbol"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="flow must be 'holdings', 'picks', or 'single_symbol'",
        )
    normalized_symbol = symbol.strip().upper() if symbol else None
    if flow == "single_symbol":
        if not normalized_symbol:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="single_symbol flow requires ?symbol=TICKER",
            )

    # Idempotency: per-flow run id (single_symbol gets a per-symbol id so two
    # different symbols can run concurrently)
    run_key = f"single_{normalized_symbol}" if flow == "single_symbol" else flow
    legacy = await _get_legacy_run(mongodb, run_key)
    if legacy is not None and legacy.status == "running":
        return legacy

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

    metadata = {"sectors": (payload.sectors if (flow == "picks" and payload) else None)}
    run, created = await run_service.create_portfolio_run(
        portfolio_key=run_key,
        metadata={key: value for key, value in metadata.items() if value is not None},
    )
    if not created:
        return _to_analysis_run(run)

    if flow == "picks":
        sectors = (payload.sectors if payload else None) or []
        background_tasks.add_task(
            _run_picks_flow,
            run_service,
            run.run_id,
            request.app,
            settings,
            sectors,
        )
    elif flow == "single_symbol":
        assert normalized_symbol is not None
        background_tasks.add_task(
            _run_single_symbol_flow,
            run_service,
            run.run_id,
            request.app,
            settings,
            normalized_symbol,
        )
    else:
        background_tasks.add_task(
            _run_holdings_flow,
            run_service,
            run.run_id,
            request.app,
            settings,
        )

    return _to_analysis_run(run)


@router.get("/status/{run_id}", response_model=AnalysisRun)
@limiter.limit("120/minute")
async def get_status(
    request: Request,
    run_id: str,
    mongodb: MongoDB = Depends(get_mongodb),
    run_repository: AgentRunRepository = Depends(get_agent_run_repository),
) -> AnalysisRun:
    if run_id not in ("holdings", "picks") and not run_id.startswith("single_"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="run_id must be 'holdings', 'picks', or 'single_<TICKER>'",
        )
    await run_repository.release_stale_portfolio_claim(run_id, now=utcnow())
    run = await run_repository.get_latest_by_portfolio_key(run_id)
    if run is not None:
        return _to_analysis_run(run)
    legacy = await _get_legacy_run(mongodb, run_id)
    if legacy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No run for {run_id}",
        )
    return legacy
