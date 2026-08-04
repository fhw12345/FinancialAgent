from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from src.agent.prompt_registry import prompt_registry_snapshot

from .live_budget import BudgetLedger
from .live_cases import load_live_cases, load_provider_smoke_cases
from .live_comparison import compare_live_reports
from .live_gateway import (
    EvaluationGateway,
    EvaluationGatewayCallError,
    FakeLiveModelGateway,
    LiveModelGateway,
)
from .live_metrics import calculate_live_metrics
from .live_policy import (
    ROUTER_MAX_INPUT_TOKENS,
    ROUTER_MAX_OUTPUT_TOKENS,
    call_reservation,
    case_reservation,
    judge_failures,
    usage_totals,
)
from .live_progress import build_running_report
from .live_schemas import (
    DeterministicRubricResult,
    LiveCaseResult,
    LiveCaseStatus,
    LiveEvaluationCase,
    LiveEvaluationReport,
    LiveEvaluationRequest,
    LiveEvaluationStatus,
    ModelUsage,
    ToolEvidence,
)
from .pricing import (
    PRICING_CATALOG_VERSION,
    MissingModelPricing,
)
from .rubric import evaluate_deterministic_rubric

__all__ = ["compare_live_reports", "run_live_evaluation"]

LiveProgressCallback = Callable[[LiveEvaluationReport], Awaitable[None]]


def _merge_versions(target: dict[str, str], source: dict[str, str]) -> None:
    for prompt_id, version in source.items():
        existing = target.get(prompt_id)
        if existing is not None and existing != version:
            raise ValueError(
                f"Conflicting prompt versions for {prompt_id}: "
                f"{existing} vs {version}"
            )
        target[prompt_id] = version


def _case_failure(
    case: LiveEvaluationCase,
    *,
    status: LiveCaseStatus,
    failure: str,
) -> LiveCaseResult:
    return LiveCaseResult(
        case_id=case.case_id,
        status=status,
        passed=False,
        critical=case.critical,
        expected_flow=case.expected_flow,
        failures=[failure],
    )


async def _run_case(
    case: LiveEvaluationCase,
    *,
    request: LiveEvaluationRequest,
    gateway: EvaluationGateway,
    budget: BudgetLedger,
) -> LiveCaseResult:
    case_usages: list[ModelUsage] = []
    used_prompts: dict[str, str] = {}
    observed_flow: str | None = None
    final_answer = ""
    tools: list[ToolEvidence] = []
    deterministic_result: DeterministicRubricResult | None = None
    try:
        required_reservation = case_reservation(gateway, request, case)
        if required_reservation > case.max_cost_usd:
            return _case_failure(
                case,
                status="budget_exhausted",
                failure=(
                    f"Worst-case reservation ${required_reservation:.6f} exceeds "
                    f"case budget ${case.max_cost_usd:.6f}"
                ),
            )
        if not budget.can_reserve(required_reservation):
            return _case_failure(
                case,
                status="budget_exhausted",
                failure=(
                    f"Insufficient run budget: requires ${required_reservation:.6f}, "
                    f"remaining ${budget.remaining_usd:.6f}"
                ),
            )

        router_reservation = call_reservation(
            gateway,
            request,
            role="router",
            max_input_tokens=ROUTER_MAX_INPUT_TOKENS,
            max_output_tokens=ROUTER_MAX_OUTPUT_TOKENS,
        )
        if not budget.can_reserve(router_reservation):
            return _case_failure(
                case,
                status="budget_exhausted",
                failure="Insufficient budget for router call",
            )
        observed_flow, router_usage, router_prompts = await gateway.classify(case)
        case_usages.append(router_usage)
        _merge_versions(used_prompts, router_prompts)
        if not budget.charge([router_usage]):
            return LiveCaseResult(
                case_id=case.case_id,
                status="budget_exhausted",
                passed=False,
                critical=case.critical,
                observed_flow=observed_flow,
                expected_flow=case.expected_flow,
                model_usages=case_usages,
                prompt_versions=used_prompts,
                duration_ms=router_usage.duration_ms,
                cost_usd=router_usage.cost_usd,
                failures=["Router call exceeded the remaining run budget"],
            )

        target_role = "simple_chat" if observed_flow == "v2" else "react_agent"
        judge_reservation = call_reservation(
            gateway,
            request,
            role="eval_judge",
            max_input_tokens=case.max_judge_input_tokens,
            max_output_tokens=case.max_judge_output_tokens,
        )
        if not case.requires_clarification:
            target_reservation = call_reservation(
                gateway,
                request,
                role=target_role,
                max_input_tokens=case.max_target_input_tokens,
                max_output_tokens=case.max_target_output_tokens,
            )
            if not budget.can_reserve(target_reservation + judge_reservation):
                return LiveCaseResult(
                    status="budget_exhausted",
                    case_id=case.case_id,
                    passed=False,
                    critical=case.critical,
                    observed_flow=observed_flow,
                    expected_flow=case.expected_flow,
                    model_usages=case_usages,
                    prompt_versions=used_prompts,
                    duration_ms=sum(usage.duration_ms for usage in case_usages),
                    cost_usd=sum(usage.cost_usd for usage in case_usages),
                    failures=["Insufficient budget for target-model call"],
                )

        case_spent_usd = sum(usage.cost_usd for usage in case_usages)
        target_cost_limit_usd = min(
            max(0.0, budget.remaining_usd - judge_reservation),
            max(
                0.0,
                case.max_cost_usd - case_spent_usd - judge_reservation,
            ),
        )
        target = await gateway.generate(
            case,
            observed_flow,
            max_cost_usd=target_cost_limit_usd,
        )
        final_answer = target.final_answer
        tools = target.tools
        case_usages.extend(target.model_usages)
        _merge_versions(used_prompts, target.prompt_versions)
        if not budget.charge(target.model_usages):
            return LiveCaseResult(
                case_id=case.case_id,
                status="budget_exhausted",
                passed=False,
                critical=case.critical,
                observed_flow=observed_flow,
                expected_flow=case.expected_flow,
                final_answer=target.final_answer,
                tools=target.tools,
                model_usages=case_usages,
                prompt_versions=used_prompts,
                duration_ms=sum(usage.duration_ms for usage in case_usages),
                cost_usd=sum(usage.cost_usd for usage in case_usages),
                failures=["Target-model call exceeded the remaining run budget"],
            )
        if target.budget_exhausted:
            return LiveCaseResult(
                case_id=case.case_id,
                status="budget_exhausted",
                passed=False,
                critical=case.critical,
                observed_flow=observed_flow,
                expected_flow=case.expected_flow,
                final_answer=target.final_answer,
                tools=target.tools,
                model_usages=case_usages,
                prompt_versions=used_prompts,
                duration_ms=sum(usage.duration_ms for usage in case_usages),
                cost_usd=sum(usage.cost_usd for usage in case_usages),
                failures=[target.error or "Target-model budget exhausted"],
            )
        if target.error:
            return LiveCaseResult(
                case_id=case.case_id,
                status="failed",
                passed=False,
                critical=case.critical,
                observed_flow=observed_flow,
                expected_flow=case.expected_flow,
                final_answer=target.final_answer,
                tools=target.tools,
                model_usages=case_usages,
                prompt_versions=used_prompts,
                duration_ms=sum(usage.duration_ms for usage in case_usages),
                cost_usd=sum(usage.cost_usd for usage in case_usages),
                failures=[target.error],
            )

        deterministic = evaluate_deterministic_rubric(
            case,
            observed_flow=observed_flow,
            final_answer=target.final_answer,
            tools=target.tools,
        )
        deterministic_result = deterministic
        policy_failures: list[str] = []
        target_input_tokens, target_output_tokens = usage_totals(target.model_usages)
        if target_input_tokens > case.max_target_input_tokens:
            policy_failures.append(
                f"Target input tokens {target_input_tokens} exceeded "
                f"{case.max_target_input_tokens}"
            )
        if target_output_tokens > case.max_target_output_tokens:
            policy_failures.append(
                f"Target output tokens {target_output_tokens} exceeded "
                f"{case.max_target_output_tokens}"
            )
        if not budget.can_reserve(judge_reservation):
            return LiveCaseResult(
                case_id=case.case_id,
                status="budget_exhausted",
                passed=False,
                critical=case.critical,
                observed_flow=observed_flow,
                expected_flow=case.expected_flow,
                final_answer=target.final_answer,
                tools=target.tools,
                deterministic_rubric=deterministic,
                model_usages=case_usages,
                prompt_versions=used_prompts,
                duration_ms=sum(usage.duration_ms for usage in case_usages),
                cost_usd=sum(usage.cost_usd for usage in case_usages),
                failures=["Insufficient budget for independent Judge call"],
            )

        judgment, judge_usage, judge_prompts = await gateway.judge(case, target)
        case_usages.append(judge_usage)
        _merge_versions(used_prompts, judge_prompts)
        if not budget.charge([judge_usage]):
            return LiveCaseResult(
                case_id=case.case_id,
                status="budget_exhausted",
                passed=False,
                critical=case.critical,
                observed_flow=observed_flow,
                expected_flow=case.expected_flow,
                final_answer=target.final_answer,
                tools=target.tools,
                deterministic_rubric=deterministic,
                judge=judgment,
                model_usages=case_usages,
                prompt_versions=used_prompts,
                duration_ms=sum(usage.duration_ms for usage in case_usages),
                cost_usd=sum(usage.cost_usd for usage in case_usages),
                failures=["Judge call exceeded the remaining run budget"],
            )
        if judge_usage.input_tokens > case.max_judge_input_tokens:
            policy_failures.append(
                f"Judge input tokens {judge_usage.input_tokens} exceeded "
                f"{case.max_judge_input_tokens}"
            )
        if judge_usage.output_tokens > case.max_judge_output_tokens:
            policy_failures.append(
                f"Judge output tokens {judge_usage.output_tokens} exceeded "
                f"{case.max_judge_output_tokens}"
            )
        failures = [
            criterion.evidence
            for criterion in deterministic.criteria
            if not criterion.passed
        ]
        failures.extend(policy_failures)
        failures.extend(
            judge_failures(
                judgment,
                answer=target.final_answer,
                minimum_score=case.minimum_judge_score,
            )
        )
        if judgment.overall_score < case.minimum_judge_score:
            failures.append(
                f"Judge score {judgment.overall_score:.3f} below "
                f"{case.minimum_judge_score:.3f}"
            )
        if deterministic.score < case.minimum_deterministic_score:
            failures.append(
                f"Deterministic score {deterministic.score:.3f} below "
                f"{case.minimum_deterministic_score:.3f}"
            )
        duration_ms = sum(usage.duration_ms for usage in case_usages)
        cost_usd = sum(usage.cost_usd for usage in case_usages)
        if duration_ms > case.max_latency_ms:
            failures.append(
                f"Latency {duration_ms:.1f}ms exceeded {case.max_latency_ms:.1f}ms"
            )
        if cost_usd > case.max_cost_usd:
            failures.append(f"Cost ${cost_usd:.6f} exceeded ${case.max_cost_usd:.6f}")
        return LiveCaseResult(
            case_id=case.case_id,
            status="completed" if not failures else "failed",
            passed=not failures,
            critical=case.critical,
            observed_flow=observed_flow,
            expected_flow=case.expected_flow,
            final_answer=target.final_answer,
            tools=target.tools,
            deterministic_rubric=deterministic,
            judge=judgment,
            model_usages=case_usages,
            prompt_versions=used_prompts,
            duration_ms=duration_ms,
            cost_usd=cost_usd,
            failures=failures,
        )
    except EvaluationGatewayCallError as exc:
        case_usages.extend(exc.usages)
        _merge_versions(used_prompts, exc.prompt_versions)
        within_budget = budget.charge(exc.usages)
        return LiveCaseResult(
            case_id=case.case_id,
            status="failed" if within_budget else "budget_exhausted",
            passed=False,
            critical=case.critical,
            observed_flow=observed_flow,
            expected_flow=case.expected_flow,
            final_answer=final_answer,
            tools=tools,
            deterministic_rubric=deterministic_result,
            model_usages=case_usages,
            prompt_versions=used_prompts,
            duration_ms=sum(usage.duration_ms for usage in case_usages),
            cost_usd=sum(usage.cost_usd for usage in case_usages),
            failures=[str(exc)],
        )
    except MissingModelPricing as exc:
        return _case_failure(case, status="failed", failure=str(exc))
    except Exception as exc:
        return LiveCaseResult(
            case_id=case.case_id,
            status="failed",
            passed=False,
            critical=case.critical,
            observed_flow=observed_flow,
            expected_flow=case.expected_flow,
            final_answer=final_answer,
            tools=tools,
            deterministic_rubric=deterministic_result,
            model_usages=case_usages,
            prompt_versions=used_prompts,
            duration_ms=sum(usage.duration_ms for usage in case_usages),
            cost_usd=sum(usage.cost_usd for usage in case_usages),
            failures=[f"{type(exc).__name__}: {exc}"],
        )


async def run_live_evaluation(
    request: LiveEvaluationRequest,
    *,
    gateway: EvaluationGateway | None = None,
    cases: list[LiveEvaluationCase] | None = None,
    run_id: str | None = None,
    created_at: datetime | None = None,
    progress_callback: LiveProgressCallback | None = None,
) -> LiveEvaluationReport:
    if not request.enabled:
        raise ValueError("Live evaluation requires explicit enabled=true consent")
    if request.lane == "provider_smoke" and gateway is None:
        raise ValueError("Provider smoke requires an injected production gateway")
    if gateway is None:
        gateway = (
            FakeLiveModelGateway(request)
            if request.lane == "fake_live"
            else LiveModelGateway(request)
        )
    default_cases = (
        load_provider_smoke_cases()
        if request.lane == "provider_smoke"
        else load_live_cases()
    )
    selected_cases = (cases if cases is not None else default_cases)[
        : request.case_limit
    ]
    budget = BudgetLedger(max_cost_usd=request.max_cost_usd)
    results: list[LiveCaseResult] = []
    used_prompts: dict[str, str] = {}
    model_routes = {
        role: gateway.model_route(role)
        for role in ("router", "simple_chat", "react_agent", "eval_judge")
    }
    started_at = created_at or datetime.now(UTC)
    resolved_run_id = run_id or f"eval_live_{uuid.uuid4().hex}"
    status: LiveEvaluationStatus = "completed"
    for index, case in enumerate(selected_cases):
        result = await _run_case(
            case,
            request=request,
            gateway=gateway,
            budget=budget,
        )
        results.append(result)
        _merge_versions(used_prompts, result.prompt_versions)
        if result.status == "budget_exhausted":
            status = "budget_exhausted"
            for skipped in selected_cases[index + 1 :]:
                results.append(
                    _case_failure(
                        skipped,
                        status="skipped",
                        failure="Skipped after evaluation budget exhaustion",
                    )
                )
        if progress_callback is not None:
            await progress_callback(
                build_running_report(
                    run_id=resolved_run_id,
                    request=request,
                    created_at=started_at,
                    results=results,
                    used_prompt_versions=used_prompts,
                    model_routes=model_routes,
                )
            )
        if status == "budget_exhausted":
            break
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
    completed_at = datetime.now(UTC)
    return LiveEvaluationReport(
        run_id=resolved_run_id,
        lane=request.lane,
        status=status,
        created_at=started_at,
        completed_at=completed_at,
        max_cost_usd=request.max_cost_usd,
        metrics=metrics,
        gates_passed=gates_passed,
        budget_exhausted=status == "budget_exhausted",
        pricing_catalog_version=PRICING_CATALOG_VERSION,
        configured_prompt_versions=prompt_registry_snapshot(),
        used_prompt_versions=used_prompts,
        model_routes=model_routes,
        results=results,
    )
