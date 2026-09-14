"""Provenance is captured on execution, survives persistence, and stays unknown for history."""

import json
from unittest.mock import patch

import pytest

from src.core.provenance import EvaluationProvenance, capture_evaluation_provenance
from src.evals.cases_v2 import load_cases
from src.evals.live_runner import run_live_evaluation
from src.evals.live_schemas import LiveEvaluationRequest
from src.evals.reporting import (
    load_live_report,
    load_report,
    write_live_reports,
    write_reports,
)
from src.evals.runner import run_deterministic_evaluation


@pytest.mark.asyncio
async def test_build_commit_is_validated(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.delenv("FINANCIAL_AGENT_COMMIT", raising=False)
    result = await capture_evaluation_provenance()
    assert result.source == "build"
    assert result.git_commit == "a" * 40
    assert result.dirty is None
    monkeypatch.setenv("GITHUB_SHA", "not-a-commit")
    with patch("src.core.provenance.REPOSITORY_ROOT", tmp_path):
        result = await capture_evaluation_provenance()
    assert result.source == "unknown"
    assert result.git_commit is None


@pytest.mark.asyncio
async def test_local_dirty_git_and_missing_tool_are_not_clean(monkeypatch, tmp_path):
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    monkeypatch.delenv("FINANCIAL_AGENT_COMMIT", raising=False)
    (tmp_path / ".git").mkdir()
    with patch("src.core.provenance.REPOSITORY_ROOT", tmp_path):
        with patch(
            "src.core.provenance.subprocess.check_output",
            side_effect=["b" * 40, " M src.py\n"],
        ):
            result = await capture_evaluation_provenance()
        assert result.dirty is True and result.source == "git"
        with patch(
            "src.core.provenance.subprocess.check_output", side_effect=FileNotFoundError
        ):
            result = await capture_evaluation_provenance()
        assert result.source == "unknown" and result.dirty is None


@pytest.mark.asyncio
async def test_deterministic_roundtrip_and_legacy_unknown(tmp_path):
    report = await run_deterministic_evaluation(load_cases())
    assert report.provenance and report.provenance.backend_version != "0.1.0"
    json_path, markdown = write_reports(report, tmp_path)
    assert load_report(json_path).provenance == report.provenance
    assert report.provenance.backend_version in markdown.read_text()
    payload = json.loads(json_path.read_text())
    payload.pop("provenance")
    json_path.write_text(json.dumps(payload))
    assert load_report(json_path).provenance is None


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [1.0, 0.000001])
async def test_live_progress_final_and_legacy_keep_identity(tmp_path, budget):
    identity = EvaluationProvenance(
        backend_version="1.2.3", git_commit="c" * 40, source="build"
    )
    progress = []

    async def save(report):
        progress.append(report)

    report = await run_live_evaluation(
        LiveEvaluationRequest(
            lane="fake_live", enabled=True, max_cost_usd=budget, case_limit=2
        ),
        provenance=identity,
        progress_callback=save,
    )
    assert progress
    assert all(item.provenance == identity for item in progress)
    assert report.provenance == identity
    if budget < 0.001:
        assert report.status == "budget_exhausted"
    json_path, markdown = write_live_reports(report, tmp_path)
    assert "1.2.3" in markdown.read_text()
    assert load_live_report(json_path).provenance == identity
    payload = json.loads(json_path.read_text())
    payload.pop("provenance")
    json_path.write_text(json.dumps(payload))
    assert load_live_report(json_path).provenance is None
