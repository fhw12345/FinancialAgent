from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage

from src.evals.cases_v2 import load_cases
from src.evals.live_cases import load_live_cases, load_provider_smoke_cases
from src.evals.live_gateway import (
    EvaluationGatewayCallError,
    FakeLiveModelGateway,
)
from src.evals.live_runner import compare_live_reports, run_live_evaluation
from src.evals.live_schemas import (
    JudgeFailure,
    LiveEvaluationCase,
    LiveEvaluationRequest,
    ModelUsage,
    QualityJudgment,
    ToolEvidence,
)
from src.evals.model_budget import (
    EvaluationBudgetExceeded,
    EvaluationModelBudgetCallback,
)
from src.evals.replay_tools import create_replay_tools
from src.evals.rubric import evaluate_deterministic_rubric
from src.evals.runner import run_deterministic_evaluation
from src.evals.schemas import GoldenCase


@pytest.mark.asyncio
async def test_fake_live_replay_evaluates_tools_quality_and_cost():
    report = await run_live_evaluation(
        LiveEvaluationRequest(
            lane="fake_live",
            enabled=True,
            max_cost_usd=1,
            case_limit=8,
        )
    )

    assert report.status == "completed"
    assert report.gates_passed is True
    assert report.metrics.case_pass_rate == 1.0
    assert report.metrics.tool_recall == 1.0
    assert report.metrics.tool_precision == 1.0
    assert report.metrics.deterministic_quality >= 0.9
    assert report.metrics.judge_quality == 1.0
    assert report.metrics.input_tokens > 0
    assert report.metrics.output_tokens > 0
    assert 0 < report.metrics.estimated_cost_usd < report.max_cost_usd
    assert report.used_prompt_versions["router"] == "router@1"
    assert report.used_prompt_versions["financial-system"] == "financial-system@4"
    assert report.used_prompt_versions["eval-judge"] == "eval-judge@1"
    quote = next(
        result for result in report.results if result.case_id == "live_quote_en"
    )
    assert [tool.tool_name for tool in quote.tools] == ["get_stock_quote"]
    assert quote.tools[0].source_id == "REPLAY-Q-AAPL-2026-08-01"


@pytest.mark.asyncio
async def test_live_eval_requires_explicit_consent():
    with pytest.raises(ValueError, match="enabled=true"):
        await run_live_evaluation(
            LiveEvaluationRequest(
                lane="fake_live",
                enabled=False,
                max_cost_usd=1,
            )
        )


@pytest.mark.asyncio
async def test_live_eval_stops_and_skips_after_budget_exhaustion():
    report = await run_live_evaluation(
        LiveEvaluationRequest(
            lane="fake_live",
            enabled=True,
            max_cost_usd=0.000001,
            case_limit=3,
        )
    )

    assert report.status == "budget_exhausted"
    assert report.budget_exhausted is True
    assert report.gates_passed is False
    assert report.results[0].status == "budget_exhausted"
    assert all(result.status == "skipped" for result in report.results[1:])


@pytest.mark.asyncio
async def test_budget_preflight_does_not_spend_on_unaffordable_case():
    request = LiveEvaluationRequest(
        lane="fake_live",
        enabled=True,
        max_cost_usd=0.000001,
        case_limit=1,
    )

    class CountingGateway(FakeLiveModelGateway):
        classify_calls = 0

        async def classify(self, case):
            self.classify_calls += 1
            return await super().classify(case)

    gateway = CountingGateway(request)
    report = await run_live_evaluation(request, gateway=gateway)

    assert report.status == "budget_exhausted"
    assert gateway.classify_calls == 0
    assert report.metrics.estimated_cost_usd == 0


@pytest.mark.asyncio
async def test_actual_cost_overrun_is_retained_as_budget_exhaustion():
    request = LiveEvaluationRequest(
        lane="fake_live",
        enabled=True,
        max_cost_usd=1,
        case_limit=1,
    )

    class OverrunGateway(FakeLiveModelGateway):
        async def classify(self, case):
            prompt = {"router": "router@1"}
            return (
                case.expected_flow,
                ModelUsage(
                    role="router",
                    provider="fake",
                    model="e2e-model",
                    input_tokens=10,
                    output_tokens=5,
                    total_tokens=15,
                    cost_usd=2,
                    duration_ms=5,
                ),
                prompt,
            )

    report = await run_live_evaluation(
        request,
        gateway=OverrunGateway(request),
    )

    assert report.status == "budget_exhausted"
    assert report.results[0].cost_usd == 2
    assert report.metrics.estimated_cost_usd == 2


@pytest.mark.asyncio
async def test_judge_requires_exact_failure_evidence():
    request = LiveEvaluationRequest(
        lane="fake_live",
        enabled=True,
        max_cost_usd=1,
        case_limit=1,
    )

    class InvalidEvidenceGateway(FakeLiveModelGateway):
        async def judge(self, case, target):
            prompt = {"eval-judge": "eval-judge@1"}
            judgment = QualityJudgment(
                factual_grounding=0.5,
                required_fact_coverage=1,
                source_consistency=1,
                relevance=1,
                completeness=1,
                uncertainty_disclosure=1,
                contradiction_handling=1,
                financial_risk_language=1,
                unsupported_certainty=1,
                overall_score=0.9,
                failures=[
                    JudgeFailure(
                        criterion="factual_grounding",
                        quote="not present in the answer",
                        reason="Synthetic unsupported statement",
                    )
                ],
            )
            return judgment, self._usage("eval_judge", 100, 30), prompt

    report = await run_live_evaluation(
        request,
        gateway=InvalidEvidenceGateway(request),
    )

    assert report.status == "failed"
    assert any(
        "not an exact answer quote" in failure for failure in report.results[0].failures
    )


@pytest.mark.asyncio
async def test_judge_timeout_preserves_target_cost_and_evidence():
    request = LiveEvaluationRequest(
        lane="fake_live",
        enabled=True,
        max_cost_usd=1,
        case_limit=1,
    )

    class TimeoutGateway(FakeLiveModelGateway):
        async def judge(self, case, target):
            raise TimeoutError("synthetic judge timeout")

    report = await run_live_evaluation(
        request,
        gateway=TimeoutGateway(request),
    )

    assert report.status == "failed"
    assert report.results[0].cost_usd > 0
    assert any("TimeoutError" in failure for failure in report.results[0].failures)


@pytest.mark.asyncio
async def test_deterministic_rubric_overrides_permissive_judge():
    request = LiveEvaluationRequest(
        lane="fake_live",
        enabled=True,
        max_cost_usd=1,
        case_limit=1,
    )
    quote_case = load_live_cases()[2]

    class PermissiveJudgeGateway(FakeLiveModelGateway):
        async def generate(self, case, observed_flow, *, max_cost_usd):
            target = await super().generate(
                case,
                observed_flow,
                max_cost_usd=max_cost_usd,
            )
            return target.model_copy(
                update={"final_answer": "AAPL data was retrieved."}
            )

    report = await run_live_evaluation(
        request,
        gateway=PermissiveJudgeGateway(request),
        cases=[quote_case],
    )

    assert report.status == "failed"
    assert report.results[0].judge is not None
    assert report.results[0].judge.overall_score == 1
    assert any("missing facts" in failure for failure in report.results[0].failures)


@pytest.mark.asyncio
async def test_created_at_tracks_run_start_instead_of_completion():
    started = datetime(2026, 8, 4, 7, 0, tzinfo=UTC)
    report = await run_live_evaluation(
        LiveEvaluationRequest(
            lane="fake_live",
            enabled=True,
            max_cost_usd=1,
            case_limit=1,
        ),
        created_at=started,
    )

    assert report.created_at == started
    assert report.completed_at is not None
    assert report.completed_at >= report.created_at


@pytest.mark.asyncio
async def test_progress_callback_persists_each_completed_case():
    snapshots = []

    async def capture(report):
        snapshots.append(report)

    report = await run_live_evaluation(
        LiveEvaluationRequest(
            lane="fake_live",
            enabled=True,
            max_cost_usd=1,
            case_limit=2,
        ),
        progress_callback=capture,
    )

    assert report.status == "completed"
    assert [len(snapshot.results) for snapshot in snapshots] == [1, 2]
    assert all(snapshot.status == "running" for snapshot in snapshots)
    assert snapshots[1].metrics.estimated_cost_usd >= (
        snapshots[0].metrics.estimated_cost_usd
    )


@pytest.mark.asyncio
async def test_invalid_paid_gateway_response_retains_usage():
    request = LiveEvaluationRequest(
        lane="fake_live",
        enabled=True,
        max_cost_usd=1,
        case_limit=1,
    )

    class InvalidGateway(FakeLiveModelGateway):
        async def classify(self, case):
            raise EvaluationGatewayCallError(
                "Invalid router structured output",
                usages=[
                    ModelUsage(
                        role="router",
                        provider="fake",
                        model="e2e-model",
                        input_tokens=50,
                        output_tokens=10,
                        total_tokens=60,
                        cost_usd=0.001,
                    )
                ],
                prompt_versions={"router": "router@1"},
            )

    report = await run_live_evaluation(
        request,
        gateway=InvalidGateway(request),
    )

    assert report.status == "failed"
    assert report.metrics.total_tokens == 60
    assert report.metrics.estimated_cost_usd == 0.001
    assert report.used_prompt_versions == {"router": "router@1"}


@pytest.mark.asyncio
async def test_model_budget_blocks_unaffordable_next_call():
    callback = EvaluationModelBudgetCallback(
        role="react_agent",
        provider="fake",
        model="e2e-model",
        max_cost_usd=0.0000001,
        max_output_tokens_per_call=100,
        pricing_overrides={},
    )

    with pytest.raises(EvaluationBudgetExceeded, match="before model call"):
        await callback.on_chat_model_start(
            {},
            [[HumanMessage(content="A" * 1000)]],
            run_id=uuid4(),
        )


def test_provider_tool_failure_and_alias_cannot_false_green():
    case = LiveEvaluationCase(
        case_id="provider_quote",
        language="en",
        input="Get the current AAPL quote.",
        current_symbol="AAPL",
        expected_flow="v3",
        required_tools=["get_stock_quote"],
        required_facts=["AAPL"],
        require_source_evidence=True,
    )
    failed = evaluate_deterministic_rubric(
        case,
        observed_flow="v3",
        final_answer="No quote data available for AAPL",
        tools=[
            ToolEvidence(
                tool_name="finnhub_quote",
                output="No quote data available for AAPL",
                success=False,
            )
        ],
    )
    passed = evaluate_deterministic_rubric(
        case,
        observed_flow="v3",
        final_answer="AAPL is $210.25 [finnhub:AAPL:2026-08-04]",
        tools=[
            ToolEvidence(
                tool_name="finnhub_quote",
                output="AAPL is $210.25 [finnhub:AAPL:2026-08-04]",
                source_id="finnhub:AAPL:2026-08-04",
                provider="finnhub",
            )
        ],
    )

    assert failed.required_tool_recall == 0
    assert any(
        criterion.criterion == "source_evidence" and not criterion.passed
        for criterion in failed.criteria
    )
    assert passed.required_tool_recall == 1
    assert all(criterion.passed for criterion in passed.criteria)


@pytest.mark.asyncio
async def test_live_baseline_enforces_latency_token_and_cost_regressions():
    baseline = await run_live_evaluation(
        LiveEvaluationRequest(
            lane="fake_live",
            enabled=True,
            max_cost_usd=1,
            case_limit=2,
        )
    )
    current = baseline.model_copy(
        update={
            "run_id": "eval_live_regressed",
            "metrics": baseline.metrics.model_copy(
                update={
                    "p95_latency_ms": baseline.metrics.p95_latency_ms + 500,
                    "total_tokens": baseline.metrics.total_tokens * 2,
                    "estimated_cost_usd": baseline.metrics.estimated_cost_usd + 0.01,
                }
            ),
        }
    )

    comparison = compare_live_reports(current, baseline)

    assert comparison.regression_gate_passed is False
    assert comparison.metrics["p95_latency_ms"].passed is False
    assert comparison.metrics["total_tokens"].passed is False
    assert comparison.metrics["estimated_cost_usd"].passed is False


@pytest.mark.asyncio
async def test_deterministic_lane_cannot_pass_with_failed_case():
    cases = [
        GoldenCase(
            case_id=f"ok_{index}",
            category="instant",
            language="en",
            input="What is diversification?",
            expected_flow="v2",
            expected_execution_mode="instant",
            max_latency_class="long",
            max_cost_class="high",
        )
        for index in range(4)
    ]
    cases.append(
        GoldenCase(
            case_id="wrong",
            category="instant",
            language="en",
            input="What is the current AAPL price?",
            expected_flow="v2",
            expected_execution_mode="instant",
            max_latency_class="long",
            max_cost_class="high",
        )
    )

    report = await run_deterministic_evaluation(cases)

    assert report.passed_cases == 4
    assert report.case_pass_rate == 0.8
    assert report.critical_case_failures == 1
    assert report.gates_passed is False


@pytest.mark.asyncio
async def test_deterministic_prompt_injection_uses_valid_symbol_fixtures():
    report = await run_deterministic_evaluation(load_cases())
    injection_results = [
        result
        for case, result in zip(load_cases(), report.results, strict=True)
        if case.expect_prompt_injection_safe
    ]

    assert len(injection_results) == 10
    assert all(result.prompt_injection_safe for result in injection_results)
    assert report.used_prompt_versions == {}
    assert report.evaluated_prompt_versions == {}
    assert "financial-system" in report.configured_prompt_versions


def test_live_suite_declares_real_tool_and_fact_contracts():
    cases = load_live_cases()

    assert len(cases) >= 8
    assert any(case.required_tools for case in cases)
    assert any(case.required_facts for case in cases)
    assert any(case.untrusted_context for case in cases)


def test_provider_smoke_uses_separate_allowlisted_contracts():
    cases = load_provider_smoke_cases()

    assert [case.case_id for case in cases] == [
        "smoke_concept_en",
        "smoke_quote_en",
    ]
    assert all(
        not any(fact.startswith("REPLAY-") for fact in case.required_facts)
        for case in cases
    )


@pytest.mark.asyncio
async def test_replay_tools_reject_unregistered_symbols():
    quote_tool = next(
        tool for tool in create_replay_tools() if tool.name == "get_stock_quote"
    )

    with pytest.raises(ValueError, match="No replay fixture"):
        await quote_tool.ainvoke({"symbol": "NVDA"})
