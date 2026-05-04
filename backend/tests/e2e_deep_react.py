"""
End-to-end test: invoke DeepReActAgent.analyze() against a real symbol with
the new cross-vendor model assignments. Captures all sub-agent invocations
and the final verdict.

Run from backend/:
    python -m tests.e2e_deep_react

Requires: Maestro at MAESTRO_BASE_URL, network access for tools.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import traceback

os.environ.setdefault("MAESTRO_BASE_URL", "http://localhost:23333/api/anthropic")
os.environ.setdefault("MAESTRO_AUTH_TOKEN", "Powered by Agent Maestro")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agent.deep_react_agent import DeepReActAgent  # noqa: E402
from src.core.config import get_settings  # noqa: E402


def collect_tools() -> list:
    """Build a minimal tool set; we just want to exercise the LLM path."""
    from langchain_core.tools import tool

    @tool
    def get_stock_quote(symbol: str) -> str:
        """Get the current stock quote for a symbol."""
        return f"{symbol} trading at $189.50, +1.2% today, vol 52M, mkt cap $2.9T."

    @tool
    def get_recent_news(symbol: str) -> str:
        """Get recent headlines for a symbol."""
        return f"Recent {symbol} news: Q4 earnings beat, new product launch, analyst upgrade."

    @tool
    def get_financials(symbol: str) -> str:
        """Get latest financial metrics for a symbol."""
        return f"{symbol}: P/E 28, ROE 145%, debt/equity 1.5, FCF margin 25%, revenue growth 8%."

    return [get_stock_quote, get_recent_news, get_financials]


def make_event_logger():
    counts: dict[str, int] = {}
    role_models: dict[str, str] = {}
    errors: list[str] = []

    def on_event(ev: dict) -> None:
        et = ev.get("type", "?")
        counts[et] = counts.get(et, 0) + 1
        if et == "subagent_start":
            role_models[ev.get("subagent", "?")] = ev.get("model", "?")
        if et in ("error", "subagent_error"):
            errors.append(f"{et}: {ev.get('error', ev)}")
        if et in (
            "subagent_start",
            "subagent_complete",
            "verdict_start",
            "verdict_complete",
            "debate_start",
            "debate_round_complete",
            "error",
        ):
            print(
                f"  [event] {et} {ev.get('subagent', '')} {ev.get('model', '')}".rstrip()
            )

    return on_event, counts, role_models, errors


async def main():
    symbol = "AAPL"
    print(f"=== Deep ReAct E2E: {symbol} ===")
    print(f"Maestro: {os.environ['MAESTRO_BASE_URL']}\n")

    settings = get_settings()
    try:
        tools = collect_tools()
        print(f"Loaded {len(tools)} tools")
    except Exception as e:
        print(f"Tool loading failed: {e}")
        tools = []

    agent = DeepReActAgent(
        settings=settings,
        tools=tools,
        enable_debate=True,
        max_debate_rounds=1,
    )

    on_event, counts, role_models, errors = make_event_logger()

    t0 = time.time()
    try:
        result = await agent.analyze(
            symbol=symbol,
            user_id="e2e-test",
            on_event=on_event,
            user_message=f"Give me a quick analysis of {symbol}.",
        )
    except Exception:
        print("\n!!! analyze() raised:")
        traceback.print_exc()
        return 1
    dt = time.time() - t0

    print(f"\n=== DONE in {dt:.1f}s ===")
    print(f"Event counts: {counts}")
    print(f"Sub-agent → model: {role_models}")
    if errors:
        print(f"\nERRORS ({len(errors)}):")
        for e in errors[:10]:
            print(f"  - {e}")
    report = (result or {}).get("research_report", "")
    print(f"\nVerdict length: {len(report)} chars")
    print(f"Verdict head: {report[:300]}")
    return 0 if not errors and report else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
