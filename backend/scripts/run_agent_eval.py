from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.evals.reporting import load_report, write_reports  # noqa: E402
from src.evals.runner import (  # noqa: E402
    compare_evaluation_reports,
    run_deterministic_evaluation,
)
from src.evals.suites import load_suite  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("artifacts/evals"))
    parser.add_argument("--suite", choices=("1.0", "2.0"), default="2.0")
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    report = await run_deterministic_evaluation(load_suite(args.suite))
    if args.baseline is not None:
        comparison = compare_evaluation_reports(
            report,
            load_report(args.baseline),
        )
        report = report.model_copy(update={"comparison": comparison})
    json_path, markdown_path = write_reports(report, args.out)
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")
    comparison_passed = (
        report.comparison is None or report.comparison.regression_gate_passed
    )
    return 0 if report.gates_passed and comparison_passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
