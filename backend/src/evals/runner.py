from __future__ import annotations

import math
import time
from typing import Any, cast

from ..agent.flow_router import AgentFlowRouter
from ..agent.prompt_registry import prompt_registry_snapshot
from ..agent.symbol_resolver import SymbolResolver
from ..core.utils.date_utils import utcnow
from .schemas import (
    CaseEvaluationResult,
    CostClass,
    EvaluationComparison,
    EvaluationGateResult,
    EvaluationMetricComparison,
    EvaluationReport,
    EvaluationThresholds,
    EvaluationVersionChange,
    ExecutionMode,
    GateOperator,
    GoldenCase,
)

FLOW_EXECUTION_MODES: dict[str, ExecutionMode] = {
    "v2": "instant",
    "v3": "agentic",
    "v4-deep": "research",
}
FLOW_COST_CLASSES: dict[str, CostClass] = {
    "v2": "none",
    "v3": "low",
    "v4-deep": "high",
}
LATENCY_BUDGETS_MS = {
    "fast": 100.0,
    "normal": 500.0,
    "long": 2000.0,
}
COST_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}
DETERMINISTIC_MODEL_ROUTES = {
    "router": "deterministic-rules:no-live-model",
    "symbol-resolution": "deterministic:no-live-model",
}


class _NoLiveClassifier:
    async def ainvoke(self, messages: Any) -> Any:
        raise RuntimeError("Live classifier is disabled in deterministic evaluation")


class _EmptySymbolSearch:
    async def exact(self, symbol: str) -> None:
        return None

    async def search(self, query: str, limit: int = 5) -> list[Any]:
        return []


async def _unknown_symbol_is_safe(case: GoldenCase) -> bool:
    settings = cast(
        Any,
        type("Settings", (), {"symbol_resolution_llm_enabled": False})(),
    )
    resolution = await SymbolResolver(
        cast(Any, _EmptySymbolSearch()),
        settings=settings,
    ).resolve(message=case.input, current_symbol=case.current_symbol)
    return (
        resolution.status in {"unresolved", "ambiguous"} and resolution.symbol is None
    )


def _nearest_rank_percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _ratio(results: list[CaseEvaluationResult], field: str) -> float:
    if not results:
        return 1.0
    return sum(bool(getattr(result, field)) for result in results) / len(results)


def _gate(
    gate_id: str,
    observed: float,
    operator: GateOperator,
    threshold: float,
) -> EvaluationGateResult:
    passed = observed >= threshold if operator == ">=" else observed <= threshold
    return EvaluationGateResult(
        gate_id=gate_id,
        passed=passed,
        observed=observed,
        operator=operator,
        threshold=threshold,
    )


async def run_deterministic_evaluation(
    cases: list[GoldenCase],
    *,
    thresholds: EvaluationThresholds | None = None,
) -> EvaluationReport:
    thresholds = thresholds or EvaluationThresholds()
    router = AgentFlowRouter(llm=_NoLiveClassifier())
    results: list[CaseEvaluationResult] = []
    for case in cases:
        started = time.perf_counter()
        decision = await router.select(
            message=case.input,
            current_symbol=case.current_symbol,
            requested_version=case.requested_policy,
        )
        router_match = decision.flow == case.expected_flow
        resolution_safe = True
        if case.expect_unknown_symbol_safe or case.expect_prompt_injection_safe:
            resolution_safe = await _unknown_symbol_is_safe(case)
        unknown_safe = resolution_safe if case.expect_unknown_symbol_safe else True
        prompt_injection_safe = (
            resolution_safe if case.expect_prompt_injection_safe else True
        )
        observed_execution_mode = FLOW_EXECUTION_MODES[decision.flow]
        execution_mode_match = observed_execution_mode == case.expected_execution_mode
        observed_cost_class = FLOW_COST_CLASSES[decision.flow]
        cost_within_budget = (
            COST_RANK[observed_cost_class] <= COST_RANK[case.max_cost_class]
        )
        duration_ms = (time.perf_counter() - started) * 1000
        latency_budget_ms = LATENCY_BUDGETS_MS[case.max_latency_class]
        latency_within_budget = duration_ms <= latency_budget_ms
        failures = []
        if not router_match:
            failures.append(
                f"Expected flow {case.expected_flow}, observed {decision.flow}"
            )
        if not execution_mode_match:
            failures.append(
                "Expected execution mode "
                f"{case.expected_execution_mode}, observed {observed_execution_mode}"
            )
        if not unknown_safe:
            failures.append("Unknown-symbol request did not stay in clarification flow")
        if not prompt_injection_safe:
            failures.append("Prompt injection changed or invented the symbol context")
        if not latency_within_budget:
            failures.append(
                f"Latency {duration_ms:.1f}ms exceeded {latency_budget_ms:.1f}ms budget"
            )
        if not cost_within_budget:
            failures.append(
                f"Observed cost class {observed_cost_class} exceeded "
                f"{case.max_cost_class}"
            )
        quality_passed = (
            router_match
            and execution_mode_match
            and unknown_safe
            and prompt_injection_safe
        )
        results.append(
            CaseEvaluationResult(
                case_id=case.case_id,
                passed=quality_passed and latency_within_budget and cost_within_budget,
                quality_passed=quality_passed,
                observed_flow=decision.flow,
                expected_flow=case.expected_flow,
                router_match=router_match,
                observed_execution_mode=observed_execution_mode,
                expected_execution_mode=case.expected_execution_mode,
                execution_mode_match=execution_mode_match,
                unknown_symbol_safe=unknown_safe,
                prompt_injection_safe=prompt_injection_safe,
                duration_ms=duration_ms,
                latency_budget_ms=latency_budget_ms,
                latency_within_budget=latency_within_budget,
                observed_cost_class=observed_cost_class,
                max_cost_class=case.max_cost_class,
                cost_within_budget=cost_within_budget,
                failures=failures,
            )
        )
    total = len(results)
    automatic_results = [
        result
        for case, result in zip(cases, results, strict=True)
        if case.requested_policy == "auto"
    ]
    router_accuracy = sum(result.router_match for result in automatic_results) / len(
        automatic_results
    )
    execution_mode_accuracy = _ratio(results, "execution_mode_match")
    safety_cases = [
        result
        for case, result in zip(cases, results, strict=True)
        if case.expect_unknown_symbol_safe
    ]
    unknown_symbol_safety = (
        sum(result.unknown_symbol_safe for result in safety_cases) / len(safety_cases)
        if safety_cases
        else 1.0
    )
    injection_cases = [
        result
        for case, result in zip(cases, results, strict=True)
        if case.expect_prompt_injection_safe
    ]
    prompt_injection_safety = _ratio(injection_cases, "prompt_injection_safe")
    quality_score = _ratio(results, "quality_passed")
    cost_policy_compliance = _ratio(results, "cost_within_budget")
    durations = [result.duration_ms for result in results]
    p95_latency_ms = _nearest_rank_percentile(durations, 0.95)
    total_duration_ms = sum(durations)
    live_model_calls = 0
    gates = [
        _gate(
            "router_accuracy",
            router_accuracy,
            ">=",
            thresholds.router_accuracy,
        ),
        _gate(
            "execution_mode_accuracy",
            execution_mode_accuracy,
            ">=",
            thresholds.execution_mode_accuracy,
        ),
        _gate(
            "unknown_symbol_safety",
            unknown_symbol_safety,
            ">=",
            thresholds.unknown_symbol_safety,
        ),
        _gate(
            "prompt_injection_safety",
            prompt_injection_safety,
            ">=",
            thresholds.prompt_injection_safety,
        ),
        _gate(
            "quality_score",
            quality_score,
            ">=",
            thresholds.quality_score,
        ),
        _gate(
            "cost_policy_compliance",
            cost_policy_compliance,
            ">=",
            thresholds.cost_policy_compliance,
        ),
        _gate(
            "p95_latency_ms",
            p95_latency_ms,
            "<=",
            thresholds.p95_latency_ms,
        ),
        _gate(
            "live_model_calls",
            float(live_model_calls),
            "<=",
            float(thresholds.max_live_model_calls),
        ),
    ]
    return EvaluationReport(
        suite_version=cases[0].suite_version if cases else "unknown",
        created_at=utcnow(),
        total_cases=total,
        passed_cases=sum(result.passed for result in results),
        router_accuracy=router_accuracy,
        execution_mode_accuracy=execution_mode_accuracy,
        unknown_symbol_safety=unknown_symbol_safety,
        prompt_injection_safety=prompt_injection_safety,
        quality_score=quality_score,
        cost_policy_compliance=cost_policy_compliance,
        p95_latency_ms=p95_latency_ms,
        total_duration_ms=total_duration_ms,
        live_model_calls=live_model_calls,
        gates_passed=all(gate.passed for gate in gates),
        thresholds=thresholds,
        gates=gates,
        evaluated_prompt_versions=prompt_registry_snapshot(),
        evaluated_model_routes=DETERMINISTIC_MODEL_ROUTES,
        results=results,
    )


def _version_changes(
    current: dict[str, str],
    baseline: dict[str, str],
) -> dict[str, EvaluationVersionChange]:
    return {
        key: EvaluationVersionChange(
            baseline=baseline.get(key),
            current=current.get(key),
        )
        for key in sorted(set(current) | set(baseline))
        if current.get(key) != baseline.get(key)
    }


def compare_evaluation_reports(
    current: EvaluationReport,
    baseline: EvaluationReport,
) -> EvaluationComparison:
    metric_specs = {
        "quality_score": False,
        "router_accuracy": False,
        "execution_mode_accuracy": False,
        "unknown_symbol_safety": False,
        "prompt_injection_safety": False,
        "cost_policy_compliance": False,
        "p95_latency_ms": True,
    }
    metric_deltas = {
        metric: EvaluationMetricComparison(
            baseline=float(getattr(baseline, metric)),
            current=float(getattr(current, metric)),
            delta=float(getattr(current, metric) - getattr(baseline, metric)),
            lower_is_better=lower_is_better,
        )
        for metric, lower_is_better in metric_specs.items()
    }
    baseline_results = {result.case_id: result for result in baseline.results}
    current_results = {result.case_id: result for result in current.results}
    shared_ids = sorted(set(baseline_results) & set(current_results))
    regressed_case_ids = [
        case_id
        for case_id in shared_ids
        if baseline_results[case_id].passed and not current_results[case_id].passed
    ]
    improved_case_ids = [
        case_id
        for case_id in shared_ids
        if not baseline_results[case_id].passed and current_results[case_id].passed
    ]
    regression_gate_passed = (
        current.gates_passed
        and current.quality_score >= baseline.quality_score
        and current.router_accuracy >= baseline.router_accuracy
        and current.unknown_symbol_safety >= baseline.unknown_symbol_safety
        and current.prompt_injection_safety >= baseline.prompt_injection_safety
        and current.cost_policy_compliance >= baseline.cost_policy_compliance
        and not regressed_case_ids
    )
    return EvaluationComparison(
        baseline_suite_version=baseline.suite_version,
        current_suite_version=current.suite_version,
        metric_deltas=metric_deltas,
        prompt_version_changes=_version_changes(
            current.evaluated_prompt_versions,
            baseline.evaluated_prompt_versions,
        ),
        model_route_changes=_version_changes(
            current.evaluated_model_routes,
            baseline.evaluated_model_routes,
        ),
        regressed_case_ids=regressed_case_ids,
        improved_case_ids=improved_case_ids,
        regression_gate_passed=regression_gate_passed,
    )
