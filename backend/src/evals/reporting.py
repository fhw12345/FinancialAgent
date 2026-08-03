from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schemas import EvaluationReport


def load_report(path: Path) -> EvaluationReport:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault(
        "execution_mode_accuracy",
        payload.get("router_accuracy", 0.0),
    )
    payload.setdefault("prompt_injection_safety", 1.0)
    total_cases = payload.get("total_cases", 0)
    passed_cases = payload.get("passed_cases", 0)
    payload.setdefault(
        "quality_score",
        passed_cases / total_cases if total_cases else 0.0,
    )
    payload.setdefault("cost_policy_compliance", 1.0)
    payload.setdefault("p95_latency_ms", 0.0)
    payload.setdefault("total_duration_ms", 0.0)
    payload.setdefault("live_model_calls", 0)
    payload.setdefault("gates", [])
    payload.setdefault("evaluated_model_routes", {})
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
        f"- Quality score: {report.quality_score:.1%}",
        f"- Router accuracy: {report.router_accuracy:.1%}",
        f"- Execution-mode accuracy: {report.execution_mode_accuracy:.1%}",
        f"- Unknown-symbol safety: {report.unknown_symbol_safety:.1%}",
        f"- Prompt-injection safety: {report.prompt_injection_safety:.1%}",
        f"- Cost-policy compliance: {report.cost_policy_compliance:.1%}",
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
            "### Prompts",
            "",
        ]
    )
    lines.extend(
        f"- `{prompt_id}`: `{version}`"
        for prompt_id, version in sorted(report.evaluated_prompt_versions.items())
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
