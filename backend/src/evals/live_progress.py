from __future__ import annotations

from datetime import UTC, datetime

from src.agent.prompt_registry import prompt_registry_snapshot
from src.core.provenance import EvaluationProvenance

from .live_metrics import calculate_live_metrics
from .live_schemas import (
    LiveCaseResult,
    LiveEvaluationReport,
    LiveEvaluationRequest,
    LiveEvaluationStatus,
)
from .pricing import PRICING_CATALOG_VERSION


def build_running_report(
    *,
    run_id: str,
    request: LiveEvaluationRequest,
    created_at: datetime,
    results: list[LiveCaseResult],
    used_prompt_versions: dict[str, str],
    model_routes: dict[str, str],
    provenance: EvaluationProvenance | None = None,
) -> LiveEvaluationReport:
    return LiveEvaluationReport(
        provenance=provenance,
        run_id=run_id,
        lane=request.lane,
        status="running",
        created_at=created_at,
        max_cost_usd=request.max_cost_usd,
        metrics=calculate_live_metrics(results),
        gates_passed=False,
        pricing_catalog_version=PRICING_CATALOG_VERSION,
        configured_prompt_versions=prompt_registry_snapshot(),
        used_prompt_versions=used_prompt_versions,
        model_routes=model_routes,
        results=list(results),
    )


def build_completed_report(
    *,
    run_id: str,
    request: LiveEvaluationRequest,
    created_at: datetime,
    results: list[LiveCaseResult],
    used_prompt_versions: dict[str, str],
    model_routes: dict[str, str],
    status: LiveEvaluationStatus,
    provenance: EvaluationProvenance,
) -> LiveEvaluationReport:
    """Retain the run-start identity through progress, success and failure."""
    metrics = calculate_live_metrics(results)
    if status != "budget_exhausted" and any(
        result.status == "failed" for result in results
    ):
        status = "failed"
    gates_passed = (
        status == "completed"
        and metrics.case_pass_rate == 1.0
        and metrics.critical_case_failures == 0
        and metrics.tool_recall >= 0.9
        and metrics.tool_precision >= 0.9
        and metrics.deterministic_quality >= 0.9
        and metrics.judge_quality >= 0.8
        and metrics.required_fact_coverage >= 0.9
        and metrics.unsupported_claim_rate == 0.0
        and metrics.estimated_cost_usd <= request.max_cost_usd
    )
    return LiveEvaluationReport(
        provenance=provenance,
        run_id=run_id,
        lane=request.lane,
        status=status,
        created_at=created_at,
        completed_at=datetime.now(UTC),
        max_cost_usd=request.max_cost_usd,
        metrics=metrics,
        gates_passed=gates_passed,
        budget_exhausted=status == "budget_exhausted",
        pricing_catalog_version=PRICING_CATALOG_VERSION,
        configured_prompt_versions=prompt_registry_snapshot(),
        used_prompt_versions=used_prompt_versions,
        model_routes=model_routes,
        results=results,
    )
