from __future__ import annotations

import json
from pathlib import Path

from .schemas import EvaluationReport


def write_reports(report: EvaluationReport, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"agent-eval-{report.created_at.strftime('%Y%m%d-%H%M%S')}"
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    json_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    failures = [result for result in report.results if not result.passed]
    lines = [
        "# Agent Evaluation Report",
        "",
        f"- Suite: `{report.suite_version}`",
        f"- Cases: {report.passed_cases}/{report.total_cases} passed",
        f"- Router accuracy: {report.router_accuracy:.1%}",
        f"- Unknown-symbol safety: {report.unknown_symbol_safety:.1%}",
        f"- Gates: {'PASS' if report.gates_passed else 'FAIL'}",
        "",
        "## Failures",
        "",
    ]
    lines.extend(
        f"- `{result.case_id}`: {'; '.join(result.failures)}" for result in failures
    )
    if not failures:
        lines.append("- None")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path
