from __future__ import annotations

import structlog
from fastapi import APIRouter, Query

from src.evals.runner import run_deterministic_evaluation
from src.evals.schemas import EvaluationReport
from src.evals.suites import SuiteVersion, load_suite

logger = structlog.get_logger()

router = APIRouter(prefix="/api/admin/evaluations", tags=["evaluations"])


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
