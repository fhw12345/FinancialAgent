from pathlib import Path
from unittest.mock import patch

import pytest

from src.evals.cases_v1 import load_cases
from src.evals.reporting import write_reports
from src.evals.runner import run_deterministic_evaluation


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
