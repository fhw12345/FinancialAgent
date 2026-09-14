#!/usr/bin/env python3
"""Opt-in hosted failure probes. Never enabled for normal PR validation."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBES = ("none", "mypy", "eval", "playwright")


def inject(root: Path, probe: str, stage: str) -> bool:
    """Modify only the disposable CI checkout, immediately before its real gate."""
    if probe not in PROBES:
        raise ValueError("Unknown CI negative control")
    if probe == "none" or probe != stage:
        return False
    if probe == "mypy":
        target = root / "backend/src/core/_ci_negative_probe.py"
        target.write_text('value: int = "intentional PH-004 type failure"\n')
    elif probe == "eval":
        target = root / "backend/src/evals/runner.py"
        text = target.read_text(encoding="utf-8")
        marker = "thresholds = thresholds or EvaluationThresholds()"
        if text.count(marker) != 1:
            raise ValueError("Evaluation probe marker drifted")
        target.write_text(
            text.replace(
                marker, "thresholds = EvaluationThresholds(router_accuracy=1.1)"
            ),
            encoding="utf-8",
        )
    else:
        target = root / "frontend/e2e/ci-hardening.spec.ts"
        with target.open("a", encoding="utf-8") as handle:
            handle.write(
                """
// Intentional hosted failure control; never committed to application source.
test("PH-004 intentional browser failure", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("nav-health")).toHaveText("INTENTIONAL_PH004_FAILURE");
});
"""
            )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=PROBES[1:])
    args = parser.parse_args()
    probe = os.environ.get("PH_CI_PROBE", "none")
    if probe != "none" and not (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    ):
        raise SystemExit("Negative controls require explicit hosted workflow dispatch")
    if inject(ROOT, probe, args.stage):
        print(
            f"Activated intentional {probe} failure; the following real gate MUST fail"
        )


if __name__ == "__main__":
    main()
