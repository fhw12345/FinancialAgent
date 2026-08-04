from __future__ import annotations

from datetime import datetime

from src.agent.prompt_registry import prompt_registry_snapshot

from .live_metrics import calculate_live_metrics
from .live_schemas import (
    LiveCaseResult,
    LiveEvaluationReport,
    LiveEvaluationRequest,
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
) -> LiveEvaluationReport:
    return LiveEvaluationReport(
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
