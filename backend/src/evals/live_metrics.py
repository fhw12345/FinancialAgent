from __future__ import annotations

import math

from .live_schemas import LiveCaseResult, LiveEvaluationMetrics


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def calculate_live_metrics(
    results: list[LiveCaseResult],
) -> LiveEvaluationMetrics:
    completed = [result for result in results if result.status != "skipped"]
    rubrics = [
        result.deterministic_rubric
        for result in completed
        if result.deterministic_rubric is not None
    ]
    judgments = [result.judge for result in completed if result.judge is not None]
    usages = [usage for result in completed for usage in result.model_usages]
    return LiveEvaluationMetrics(
        case_pass_rate=(
            sum(result.passed for result in completed) / len(completed)
            if completed
            else 0.0
        ),
        critical_case_failures=sum(
            1 for result in completed if result.critical and not result.passed
        ),
        tool_recall=_average([rubric.required_tool_recall for rubric in rubrics]),
        tool_precision=_average([rubric.tool_precision for rubric in rubrics]),
        deterministic_quality=_average([rubric.score for rubric in rubrics]),
        judge_quality=_average([judgment.overall_score for judgment in judgments]),
        required_fact_coverage=_average(
            [rubric.required_fact_coverage for rubric in rubrics]
        ),
        unsupported_claim_rate=_average(
            [rubric.unsupported_claim_rate for rubric in rubrics]
        ),
        p95_latency_ms=_percentile(
            [result.duration_ms for result in completed],
            0.95,
        ),
        input_tokens=sum(usage.input_tokens for usage in usages),
        output_tokens=sum(usage.output_tokens for usage in usages),
        total_tokens=sum(usage.total_tokens for usage in usages),
        estimated_cost_usd=sum(usage.cost_usd for usage in usages),
    )
