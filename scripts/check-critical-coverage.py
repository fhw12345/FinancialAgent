#!/usr/bin/env python3
"""Enforce risk-based coverage floors for critical orchestration modules."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1] / "backend" / "coverage.json"
THRESHOLDS = {
    "src/agent/langgraph_react_agent.py": 60.0,
    "src/agent/portfolio/flows.py": 55.0,
    "src/agent/portfolio/phase1_research.py": 65.0,
    "src/agent/portfolio/phase2_decisions.py": 65.0,
    "src/agent/portfolio/phase3_execution.py": 65.0,
    "src/agent/optimizer/plan_builder.py": 60.0,
    "src/agent/optimizer/executor.py": 60.0,
    "src/services/data_manager/manager.py": 70.0,
}


def main() -> int:
    if not REPORT.is_file():
        print(f"Coverage report not found: {REPORT}", file=sys.stderr)
        return 2
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    files = report.get("files", {})
    failures: list[str] = []
    for path, floor in THRESHOLDS.items():
        summary = files.get(path, {}).get("summary", {})
        actual = float(summary.get("percent_covered", 0.0))
        print(f"{path}: {actual:.2f}% (minimum {floor:.2f}%)")
        if actual < floor:
            failures.append(f"{path}: {actual:.2f}% < {floor:.2f}%")
    if failures:
        print("Critical coverage gate failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
