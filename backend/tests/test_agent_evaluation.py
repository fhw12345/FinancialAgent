import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.evals.cases_v1 import load_cases
from src.evals.cases_v2 import load_cases as load_v2_cases
from src.evals.reporting import load_report, write_reports
from src.evals.runner import (
    compare_evaluation_reports,
    run_deterministic_evaluation,
)


def test_v1_suite_has_required_category_counts():
    cases = load_cases()
    assert len(cases) == 70
    assert sum(case.category == "instant" for case in cases) == 20
    assert sum(case.category == "agentic" for case in cases) == 20
    assert sum(case.category == "deep" for case in cases) == 15
    assert sum(case.category == "adversarial" for case in cases) == 15


@pytest.mark.asyncio
async def test_deterministic_suite_passes_router_and_safety_gates(tmp_path: Path):
    with patch(
        "src.agent.flow_router.get_llm",
        side_effect=AssertionError("live router model must not be constructed"),
    ):
        report = await run_deterministic_evaluation(load_cases())
    json_path, markdown_path = write_reports(report, tmp_path)

    assert report.gates_passed is True
    assert report.router_accuracy >= report.thresholds.router_accuracy
    assert report.unknown_symbol_safety == 1.0
    assert report.passed_cases >= 55
    assert json_path.exists()
    assert "Gates: PASS" in markdown_path.read_text(encoding="utf-8")


def test_v2_suite_adds_prompt_injection_cases():
    cases = load_v2_cases()
    injection_cases = [case for case in cases if case.expect_prompt_injection_safe]

    assert len(cases) == 80
    assert len(injection_cases) == 10
    assert all(case.expect_unknown_symbol_safe for case in injection_cases)
    assert all(case.suite_version == "2.0" for case in cases)


@pytest.mark.asyncio
async def test_v2_suite_passes_quality_latency_cost_and_injection_gates():
    with patch(
        "src.agent.flow_router.get_llm",
        side_effect=AssertionError("live router model must not be constructed"),
    ):
        report = await run_deterministic_evaluation(load_v2_cases())

    assert report.gates_passed is True
    assert report.prompt_injection_safety == 1.0
    assert report.cost_policy_compliance == 1.0
    assert report.live_model_calls == 0
    assert report.p95_latency_ms <= report.thresholds.p95_latency_ms
    assert all(gate.passed for gate in report.gates)
    assert report.evaluated_prompt_versions["router"] == "router@1"
    assert report.evaluated_model_routes["router"].endswith("no-live-model")


@pytest.mark.asyncio
async def test_report_comparison_detects_case_regression():
    report = await run_deterministic_evaluation(load_v2_cases())
    first = report.results[0].model_copy(
        update={"passed": False, "failures": ["synthetic regression"]}
    )
    regressed = report.model_copy(update={"results": [first, *report.results[1:]]})

    comparison = compare_evaluation_reports(regressed, report)

    assert comparison.regression_gate_passed is False
    assert comparison.regressed_case_ids == [first.case_id]
    assert comparison.prompt_version_changes == {}
    assert comparison.model_route_changes == {}


@pytest.mark.asyncio
async def test_reports_render_gates_comparison_and_load_legacy_json(tmp_path: Path):
    baseline = await run_deterministic_evaluation(load_v2_cases())
    comparison = compare_evaluation_reports(baseline, baseline)
    report = baseline.model_copy(update={"comparison": comparison})
    json_path, markdown_path = write_reports(report, tmp_path)
    markdown = markdown_path.read_text(encoding="utf-8")

    assert "## Gates" in markdown
    assert "## Baseline Comparison" in markdown
    assert "Regression gate: PASS" in markdown

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    for key in (
        "execution_mode_accuracy",
        "prompt_injection_safety",
        "quality_score",
        "cost_policy_compliance",
        "p95_latency_ms",
        "gates",
        "evaluated_model_routes",
        "comparison",
    ):
        payload.pop(key)
    payload["thresholds"] = {
        "router_accuracy": payload["thresholds"]["router_accuracy"],
        "unknown_symbol_safety": payload["thresholds"]["unknown_symbol_safety"],
    }
    for result in payload["results"]:
        for key in (
            "quality_passed",
            "observed_execution_mode",
            "expected_execution_mode",
            "execution_mode_match",
            "prompt_injection_safe",
            "duration_ms",
            "latency_budget_ms",
            "latency_within_budget",
            "observed_cost_class",
            "max_cost_class",
            "cost_within_budget",
        ):
            result.pop(key)
    legacy_path = tmp_path / "legacy.json"
    legacy_path.write_text(json.dumps(payload), encoding="utf-8")

    legacy = load_report(legacy_path)
    assert legacy.execution_mode_accuracy == legacy.router_accuracy
    assert legacy.prompt_injection_safety == 1.0
    assert legacy.cost_policy_compliance == 1.0
