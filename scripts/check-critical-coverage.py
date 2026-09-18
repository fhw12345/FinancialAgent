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
    "src/models/decision_assessment.py": 90.0,
    "src/services/decision_policy/builder.py": 85.0,
    "src/models/decision_review.py": 95.0,
    "src/services/decision_policy/control.py": 90.0,
    "src/services/decision_policy/policies.py": 90.0,
    "src/services/decision_policy/evidence_gate.py": 90.0,
    "src/services/decision_policy/review_gate.py": 90.0,
    "src/services/decision_policy/review_projection.py": 90.0,
    "src/services/decision_policy/review_service.py": 90.0,
    "src/services/decision_policy/review_storage.py": 90.0,
    "src/api/portfolio/reviews.py": 90.0,
    "src/database/repositories/decision_assessment_repository.py": 85.0,
    "src/models/portfolio_risk.py": 95.0,
    "src/services/portfolio_risk/estimator.py": 95.0,
    "src/services/portfolio_risk/allocation.py": 90.0,
    "src/services/portfolio_risk/provider.py": 85.0,
    "src/services/portfolio_risk/service.py": 80.0,
    "src/models/evidence.py": 95.0,
    "src/database/repositories/evidence_repository.py": 85.0,
    "src/services/evidence/claims.py": 95.0,
    "src/services/evidence/identity.py": 90.0,
    "src/services/evidence/adapters.py": 85.0,
    "src/services/evidence/collection.py": 90.0,
    "src/services/evidence/context.py": 75.0,
    "src/services/evidence/service.py": 85.0,
    "src/models/research_strategy.py": 95.0,
    "src/services/research_strategy/calculators.py": 90.0,
    "src/services/research_strategy/evaluation.py": 85.0,
    "src/services/research_strategy/store.py": 85.0,
    "src/services/research_strategy/adapters.py": 90.0,
    "src/services/research_strategy/service.py": 85.0,
    "src/services/research_strategy/monitoring.py": 85.0,
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
