from __future__ import annotations

from typing import Any, cast

from ..agent.flow_router import AgentFlowRouter
from ..agent.prompt_registry import prompt_registry_snapshot
from ..agent.symbol_resolver import SymbolResolver
from ..core.utils.date_utils import utcnow
from .schemas import (
    CaseEvaluationResult,
    EvaluationReport,
    EvaluationThresholds,
    GoldenCase,
)


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


async def run_deterministic_evaluation(
    cases: list[GoldenCase],
    *,
    thresholds: EvaluationThresholds | None = None,
) -> EvaluationReport:
    thresholds = thresholds or EvaluationThresholds()
    router = AgentFlowRouter(llm=_NoLiveClassifier())
    results: list[CaseEvaluationResult] = []
    for case in cases:
        decision = await router.select(
            message=case.input,
            current_symbol=case.current_symbol,
            requested_version=case.requested_policy,
        )
        router_match = decision.flow == case.expected_flow
        unknown_safe = (
            await _unknown_symbol_is_safe(case)
            if case.expect_unknown_symbol_safe
            else True
        )
        failures = []
        if not router_match:
            failures.append(
                f"Expected flow {case.expected_flow}, observed {decision.flow}"
            )
        if not unknown_safe:
            failures.append("Unknown-symbol request did not stay in clarification flow")
        results.append(
            CaseEvaluationResult(
                case_id=case.case_id,
                passed=router_match and unknown_safe,
                observed_flow=decision.flow,
                expected_flow=case.expected_flow,
                router_match=router_match,
                unknown_symbol_safe=unknown_safe,
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
    return EvaluationReport(
        suite_version="1.0",
        created_at=utcnow(),
        total_cases=total,
        passed_cases=sum(result.passed for result in results),
        router_accuracy=router_accuracy,
        unknown_symbol_safety=unknown_symbol_safety,
        gates_passed=(
            router_accuracy >= thresholds.router_accuracy
            and unknown_symbol_safety >= thresholds.unknown_symbol_safety
        ),
        thresholds=thresholds,
        evaluated_prompt_versions=prompt_registry_snapshot(),
        results=results,
    )
