from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .live_schemas import LiveEvaluationReport
from .schemas import EvaluationReport


def load_report(path: Path) -> EvaluationReport:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    total_cases = payload.get("total_cases", 0)
    passed_cases = payload.get("passed_cases", 0)
    payload.setdefault(
        "execution_mode_accuracy",
        payload.get("router_accuracy", 0.0),
    )
    payload.setdefault(
        "case_pass_rate",
        passed_cases / total_cases if total_cases else 0.0,
    )
    payload.setdefault("critical_case_failures", 0)
    payload.setdefault("prompt_injection_safety", 1.0)
    payload.setdefault(
        "quality_score",
        passed_cases / total_cases if total_cases else 0.0,
    )
    payload.setdefault("cost_policy_compliance", 1.0)
    payload.setdefault("latency_policy_compliance", 1.0)
    payload.setdefault("p95_latency_ms", 0.0)
    payload.setdefault("total_duration_ms", 0.0)
    payload.setdefault("live_model_calls", 0)
    payload.setdefault("gates", [])
    payload.setdefault("evaluated_model_routes", {})
    legacy_prompts = payload.get("evaluated_prompt_versions", {})
    payload.setdefault("configured_prompt_versions", legacy_prompts)
    payload.setdefault("used_prompt_versions", legacy_prompts)
    payload.setdefault("comparison", None)
    return EvaluationReport.model_validate(payload)


def write_reports(report: EvaluationReport, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"agent-eval-{report.created_at.strftime('%Y%m%d-%H%M%S')}"
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    json_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    failures = [result for result in report.results if not result.passed]
    lines = [
        "# Agent Evaluation Report",
        "",
        f"- Suite: `{report.suite_version}`",
        f"- Cases: {report.passed_cases}/{report.total_cases} passed",
        f"- Case pass rate: {report.case_pass_rate:.1%}",
        f"- Critical case failures: {report.critical_case_failures}",
        f"- Quality score: {report.quality_score:.1%}",
        f"- Router accuracy: {report.router_accuracy:.1%}",
        f"- Execution-mode accuracy: {report.execution_mode_accuracy:.1%}",
        f"- Unknown-symbol safety: {report.unknown_symbol_safety:.1%}",
        f"- Prompt-injection safety: {report.prompt_injection_safety:.1%}",
        f"- Cost-policy compliance: {report.cost_policy_compliance:.1%}",
        f"- Latency-policy compliance: {report.latency_policy_compliance:.1%}",
        f"- P95 latency: {report.p95_latency_ms:.1f} ms",
        f"- Live model calls: {report.live_model_calls}",
        f"- Gates: {'PASS' if report.gates_passed else 'FAIL'}",
        "",
        "## Gates",
        "",
        "| Gate | Observed | Requirement | Result |",
        "| --- | ---: | ---: | --- |",
    ]
    lines.extend(
        "| `{}` | {:.4g} | {} {:.4g} | {} |".format(
            gate.gate_id,
            gate.observed,
            gate.operator,
            gate.threshold,
            "PASS" if gate.passed else "FAIL",
        )
        for gate in report.gates
    )
    lines.extend(
        [
            "",
            "## Prompt and Model Routes",
            "",
            "### Used prompts",
            "",
        ]
    )
    lines.extend(
        f"- `{prompt_id}`: `{version}`"
        for prompt_id, version in sorted(report.used_prompt_versions.items())
    )
    if not report.used_prompt_versions:
        lines.append("- None (deterministic lane does not invoke model prompts)")
    lines.extend(["", "### Configured prompts", ""])
    lines.extend(
        f"- `{prompt_id}`: `{version}`"
        for prompt_id, version in sorted(report.configured_prompt_versions.items())
    )
    lines.extend(["", "### Model routes", ""])
    lines.extend(
        f"- `{route}`: `{model}`"
        for route, model in sorted(report.evaluated_model_routes.items())
    )
    if report.comparison is not None:
        comparison = report.comparison
        lines.extend(
            [
                "",
                "## Baseline Comparison",
                "",
                f"- Baseline suite: `{comparison.baseline_suite_version}`",
                f"- Regression gate: "
                f"{'PASS' if comparison.regression_gate_passed else 'FAIL'}",
                f"- Regressed cases: "
                f"{', '.join(comparison.regressed_case_ids) or 'None'}",
                f"- Improved cases: "
                f"{', '.join(comparison.improved_case_ids) or 'None'}",
                "",
                "| Metric | Baseline | Current | Delta |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        lines.extend(
            f"| `{metric}` | {delta.baseline:.4g} | {delta.current:.4g} | "
            f"{delta.delta:+.4g} |"
            for metric, delta in sorted(comparison.metric_deltas.items())
        )
    lines.extend(
        [
            "",
            "## Failures",
            "",
        ]
    )
    lines.extend(
        f"- `{result.case_id}`: {'; '.join(result.failures)}" for result in failures
    )
    if not failures:
        lines.append("- None")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path


def write_live_reports(
    report: LiveEvaluationReport,
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"agent-live-eval-{report.created_at.strftime('%Y%m%d-%H%M%S')}"
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    json_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    metrics = report.metrics
    lines = [
        "# Live Agent Evaluation Report",
        "",
        f"- Run: `{report.run_id}`",
        f"- Lane: `{report.lane}`",
        f"- Status: `{report.status}`",
        f"- Gates: {'PASS' if report.gates_passed else 'FAIL'}",
        f"- Case pass rate: {metrics.case_pass_rate:.1%}",
        f"- Critical failures: {metrics.critical_case_failures}",
        f"- Tool recall: {metrics.tool_recall:.1%}",
        f"- Tool precision: {metrics.tool_precision:.1%}",
        f"- Deterministic quality: {metrics.deterministic_quality:.1%}",
        f"- Judge quality: {metrics.judge_quality:.1%}",
        f"- Required-fact coverage: {metrics.required_fact_coverage:.1%}",
        f"- Unsupported-claim rate: {metrics.unsupported_claim_rate:.1%}",
        f"- P95 latency: {metrics.p95_latency_ms:.1f} ms",
        f"- Tokens: {metrics.input_tokens} input / " f"{metrics.output_tokens} output",
        f"- Estimated cost: ${metrics.estimated_cost_usd:.6f} / "
        f"${report.max_cost_usd:.6f}",
        f"- Pricing catalog: `{report.pricing_catalog_version}`",
        "",
        "## Used Prompts",
        "",
    ]
    lines.extend(
        f"- `{prompt_id}`: `{version}`"
        for prompt_id, version in sorted(report.used_prompt_versions.items())
    )
    if not report.used_prompt_versions:
        lines.append("- None")
    lines.extend(["", "## Configured Prompts", ""])
    lines.extend(
        f"- `{prompt_id}`: `{version}`"
        for prompt_id, version in sorted(report.configured_prompt_versions.items())
    )
    lines.extend(["", "## Model Routes", ""])
    lines.extend(
        f"- `{role}`: `{model}`" for role, model in sorted(report.model_routes.items())
    )
    lines.extend(["", "## Cases", ""])
    if report.comparison is not None:
        lines.extend(
            [
                "",
                "## Baseline Comparison",
                "",
                f"- Baseline: `{report.comparison.baseline_run_id}`",
                f"- Regression gate: "
                f"{'PASS' if report.comparison.regression_gate_passed else 'FAIL'}",
                f"- Regressed cases: "
                f"{', '.join(report.comparison.regressed_case_ids) or 'None'}",
                "",
            ]
        )
    for result in report.results:
        lines.extend(
            [
                f"### `{result.case_id}`",
                "",
                f"- Status: `{result.status}`",
                f"- Passed: `{result.passed}`",
                f"- Flow: `{result.observed_flow}` / expected "
                f"`{result.expected_flow}`",
                f"- Tools: "
                f"{', '.join(f'{tool.tool_name} [{tool.source_id or tool.provider or "unknown"}]' for tool in result.tools) or 'None'}",
                f"- Cost: `${result.cost_usd:.6f}`",
                f"- Tokens: "
                f"{sum(usage.input_tokens for usage in result.model_usages)} input / "
                f"{sum(usage.output_tokens for usage in result.model_usages)} output",
                f"- Deterministic score: "
                f"{result.deterministic_rubric.score if result.deterministic_rubric else 'N/A'}",
                f"- Judge score: "
                f"{result.judge.overall_score if result.judge else 'N/A'}",
                f"- Failures: {'; '.join(result.failures) or 'None'}",
                "",
            ]
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path


def load_live_report(path: Path) -> LiveEvaluationReport:
    return LiveEvaluationReport.model_validate_json(path.read_text(encoding="utf-8"))
