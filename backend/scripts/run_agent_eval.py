from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.evals.live_runner import (  # noqa: E402
    compare_live_reports,
    run_live_evaluation,
)
from src.evals.live_schemas import (  # noqa: E402
    LiveEvaluationRequest,
    ModelPricingOverride,
)
from src.evals.reporting import (  # noqa: E402
    load_live_report,
    load_report,
    write_live_reports,
    write_reports,
)
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
    parser.add_argument(
        "--lane",
        choices=("deterministic", "replay_live"),
        default="deterministic",
    )
    parser.add_argument("--enable-live", action="store_true")
    parser.add_argument("--max-cost-usd", type=float, default=0.25)
    parser.add_argument("--case-limit", type=int, default=8)
    parser.add_argument(
        "--pricing-override",
        action="append",
        default=[],
        metavar="MODEL:INPUT_PER_M:OUTPUT_PER_M",
    )
    args = parser.parse_args()
    if args.lane == "replay_live":
        overrides: dict[str, ModelPricingOverride] = {}
        for raw_override in args.pricing_override:
            model, input_price, output_price = raw_override.rsplit(":", 2)
            overrides[model] = ModelPricingOverride(
                input_per_million_usd=float(input_price),
                output_per_million_usd=float(output_price),
            )
        report = await run_live_evaluation(
            LiveEvaluationRequest(
                lane="replay_live",
                enabled=args.enable_live,
                max_cost_usd=args.max_cost_usd,
                case_limit=args.case_limit,
                pricing_overrides=overrides,
            )
        )
        if args.baseline is not None:
            report = report.model_copy(
                update={
                    "comparison": compare_live_reports(
                        report,
                        load_live_report(args.baseline),
                    )
                }
            )
        json_path, markdown_path = write_live_reports(report, args.out)
        print(f"JSON report: {json_path}")
        print(f"Markdown report: {markdown_path}")
        comparison_passed = (
            report.comparison is None or report.comparison.regression_gate_passed
        )
        return 0 if report.gates_passed and comparison_passed else 1

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
