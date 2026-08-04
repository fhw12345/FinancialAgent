from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request

from src.core.config import Settings, get_settings
from src.database.mongodb import MongoDB
from src.database.repositories.evaluation_run_repository import (
    EVALUATION_RUNS_COLLECTION,
    EvaluationRunRepository,
)
from src.evals.live_runner import run_live_evaluation
from src.evals.live_schemas import (
    EvaluationRunSummary,
    LiveEvaluationCapabilities,
    LiveEvaluationMetrics,
    LiveEvaluationReport,
    LiveEvaluationRequest,
)
from src.evals.provider_smoke_gateway import ProviderSmokeGateway
from src.evals.runner import run_deterministic_evaluation
from src.evals.schemas import EvaluationReport
from src.evals.suites import SuiteVersion, load_suite

from .dependencies.storage import get_mongodb

logger = structlog.get_logger()

router = APIRouter(prefix="/api/admin/evaluations", tags=["evaluations"])
STALE_RUN_AFTER = timedelta(hours=4)


def get_evaluation_repository(
    mongodb: MongoDB = Depends(get_mongodb),
) -> EvaluationRunRepository:
    return EvaluationRunRepository(mongodb.get_collection(EVALUATION_RUNS_COLLECTION))


def _summary(report: LiveEvaluationReport) -> EvaluationRunSummary:
    return EvaluationRunSummary(
        run_id=report.run_id,
        suite_version=report.suite_version,
        lane=report.lane,
        status=report.status,
        created_at=report.created_at,
        completed_at=report.completed_at,
        gates_passed=report.gates_passed,
        case_pass_rate=report.metrics.case_pass_rate,
        estimated_cost_usd=report.metrics.estimated_cost_usd,
    )


async def _expire_stale_runs(repository: EvaluationRunRepository) -> None:
    await repository.fail_stale_running(datetime.now(UTC) - STALE_RUN_AFTER)


@router.post("/run", response_model=EvaluationReport)
async def run_agent_evaluation(
    suite: SuiteVersion = Query(default="2.0"),
) -> EvaluationReport:
    report = await run_deterministic_evaluation(load_suite(suite))
    logger.info(
        "deterministic_agent_evaluation_completed",
        suite=report.suite_version,
        total_cases=report.total_cases,
        passed_cases=report.passed_cases,
        gates_passed=report.gates_passed,
    )
    return report


@router.post("/live/runs", response_model=EvaluationRunSummary, status_code=202)
async def start_live_evaluation(
    payload: LiveEvaluationRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    settings: Settings = Depends(get_settings),
    repository: EvaluationRunRepository = Depends(get_evaluation_repository),
) -> EvaluationRunSummary:
    if not payload.enabled:
        raise HTTPException(
            status_code=422,
            detail="Live evaluation requires explicit enabled=true consent",
        )
    if payload.lane == "fake_live" and settings.environment != "test":
        raise HTTPException(
            status_code=403,
            detail="fake_live is available only in the test environment",
        )
    if payload.lane == "provider_smoke" and not getattr(
        request.app.state,
        "react_agent",
        None,
    ):
        raise HTTPException(
            status_code=503,
            detail="Production ReAct agent is not available",
        )

    await repository.ensure_indexes()
    await _expire_stale_runs(repository)
    run_id = f"eval_live_{uuid.uuid4().hex}"
    created_at = datetime.now(UTC)
    initial = LiveEvaluationReport(
        run_id=run_id,
        lane=payload.lane,
        status="running",
        created_at=created_at,
        max_cost_usd=payload.max_cost_usd,
        metrics=LiveEvaluationMetrics(),
        gates_passed=False,
    )
    await repository.save(initial)

    async def execute() -> None:
        try:
            gateway = (
                ProviderSmokeGateway(payload, request.app.state.react_agent)
                if payload.lane == "provider_smoke"
                else None
            )
            report = await run_live_evaluation(
                payload,
                gateway=gateway,
                run_id=run_id,
                created_at=created_at,
                progress_callback=repository.save,
            )
        except Exception as exc:
            logger.exception(
                "live_evaluation_failed",
                run_id=run_id,
                lane=payload.lane,
            )
            report = initial.model_copy(
                update={
                    "status": "failed",
                    "completed_at": datetime.now(UTC),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        await repository.save(report)

    background_tasks.add_task(execute)
    return _summary(initial)


@router.get("/live/runs", response_model=list[EvaluationRunSummary])
async def list_live_evaluations(
    limit: int = Query(default=20, ge=1, le=100),
    repository: EvaluationRunRepository = Depends(get_evaluation_repository),
) -> list[EvaluationRunSummary]:
    await repository.ensure_indexes()
    await _expire_stale_runs(repository)
    return await repository.list(limit=limit)


@router.get("/live/capabilities", response_model=LiveEvaluationCapabilities)
async def get_live_evaluation_capabilities(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> LiveEvaluationCapabilities:
    return LiveEvaluationCapabilities(
        fake_live_available=settings.environment == "test",
        provider_smoke_available=bool(getattr(request.app.state, "react_agent", None)),
    )


@router.get("/live/runs/{run_id}", response_model=LiveEvaluationReport)
async def get_live_evaluation(
    run_id: str,
    repository: EvaluationRunRepository = Depends(get_evaluation_repository),
) -> LiveEvaluationReport:
    await _expire_stale_runs(repository)
    report = await repository.get(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return report
