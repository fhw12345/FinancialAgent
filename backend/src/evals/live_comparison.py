from __future__ import annotations

from .live_schemas import (
    LiveEvaluationComparison,
    LiveEvaluationReport,
    LiveMetricComparison,
)


def compare_live_reports(
    current: LiveEvaluationReport,
    baseline: LiveEvaluationReport,
) -> LiveEvaluationComparison:
    policies = {
        "case_pass_rate": (False, 0.0, 0.0),
        "tool_recall": (False, 0.0, 0.0),
        "tool_precision": (False, 0.0, 0.0),
        "deterministic_quality": (False, 0.05, 0.0),
        "judge_quality": (False, 0.05, 0.0),
        "required_fact_coverage": (False, 0.0, 0.0),
        "unsupported_claim_rate": (True, 0.0, 0.0),
        "p95_latency_ms": (True, 0.25, 100.0),
        "total_tokens": (True, 0.2, 100.0),
        "estimated_cost_usd": (True, 0.2, 0.005),
    }
    metrics: dict[str, LiveMetricComparison] = {}
    for name, (
        lower_is_better,
        relative_tolerance,
        absolute_tolerance,
    ) in policies.items():
        baseline_value = float(getattr(baseline.metrics, name))
        current_value = float(getattr(current.metrics, name))
        if lower_is_better:
            allowed = max(
                baseline_value * (1 + relative_tolerance),
                baseline_value + absolute_tolerance,
            )
            passed = current_value <= allowed
        else:
            allowed = min(
                baseline_value * (1 - relative_tolerance),
                baseline_value - absolute_tolerance,
            )
            passed = current_value >= allowed
        metrics[name] = LiveMetricComparison(
            baseline=baseline_value,
            current=current_value,
            delta=current_value - baseline_value,
            allowed_current=allowed,
            passed=passed,
            lower_is_better=lower_is_better,
        )
    baseline_results = {result.case_id: result for result in baseline.results}
    current_results = {result.case_id: result for result in current.results}
    shared = sorted(set(baseline_results) & set(current_results))
    regressed = [
        case_id
        for case_id in shared
        if baseline_results[case_id].passed and not current_results[case_id].passed
    ]
    improved = [
        case_id
        for case_id in shared
        if not baseline_results[case_id].passed and current_results[case_id].passed
    ]
    return LiveEvaluationComparison(
        baseline_run_id=baseline.run_id,
        current_run_id=current.run_id,
        metrics=metrics,
        regressed_case_ids=regressed,
        improved_case_ids=improved,
        regression_gate_passed=(
            current.gates_passed
            and all(metric.passed for metric in metrics.values())
            and not regressed
        ),
    )
