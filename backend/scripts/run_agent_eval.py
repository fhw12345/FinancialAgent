from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.evals.cases_v1 import load_cases  # noqa: E402
from src.evals.reporting import write_reports  # noqa: E402
from src.evals.runner import run_deterministic_evaluation  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("artifacts/evals"))
    args = parser.parse_args()
    report = await run_deterministic_evaluation(load_cases())
    json_path, markdown_path = write_reports(report, args.out)
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")
    return 0 if report.gates_passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
