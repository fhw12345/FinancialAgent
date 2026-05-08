"""W1.9 — Fibonacci sanity gate (range_position field).

Verifies that when the current price has broken out of the swing
range used to compute the Fibonacci levels by more than 5%, the
tool output (a) sets range_position to above_range / below_range,
and (b) emits a STALE FIB SWING warning telling the LLM not to
cite the levels.

The reviewer's example: AAPL with swing 277.84 → 243.42 and current
price 288.95 (~9% above swing high) was being quoted as "support
at $264 (golden zone)" — that level is stale once price has cleared
the entire range.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _build_tool(current_price: float, low: float = 100.0, high: float = 150.0):
    """Construct the fibonacci_analysis_tool with a mocked analyzer."""
    from src.agent.langgraph_react_agent import FinancialAnalysisReActAgent

    agent = FinancialAnalysisReActAgent.__new__(FinancialAnalysisReActAgent)
    analyzer = MagicMock()
    fake_result = SimpleNamespace(
        raw_data={
            "top_trends": [
                {
                    "type": "Uptrend",
                    "high": high,
                    "low": low,
                    "period": "2025-01-01 to 2025-04-01",
                }
            ]
        },
        pressure_zone={
            # 61.8% retracement of an uptrend $100 → $150 = 150 - 0.618 * 50 = 119.1
            "upper_bound": low + 0.385 * (high - low),  # ~119.25
            "lower_bound": low + 0.382 * (high - low),  # ~119.10
        },
        current_price=current_price,
    )
    analyzer.analyze = AsyncMock(return_value=fake_result)
    agent.fibonacci_analyzer = analyzer
    return agent._create_fibonacci_tool()


@pytest.mark.asyncio
async def test_in_range_no_warning() -> None:
    tool = _build_tool(current_price=125.0, low=100.0, high=150.0)
    out = await tool.ainvoke({"symbol": "AAPL"})
    assert "range_position: in_range" in out
    assert "STALE FIB SWING" not in out


@pytest.mark.asyncio
async def test_above_range_5pct_emits_warning() -> None:
    # 9% above swing high — the AAPL reviewer scenario.
    tool = _build_tool(current_price=163.5, low=100.0, high=150.0)
    out = await tool.ainvoke({"symbol": "AAPL"})
    assert "range_position: above_range" in out
    assert "STALE FIB SWING" in out
    assert "DO NOT cite" in out


@pytest.mark.asyncio
async def test_above_range_within_5pct_no_warning() -> None:
    # 3% above — within tolerance, fib still considered usable.
    tool = _build_tool(current_price=154.5, low=100.0, high=150.0)
    out = await tool.ainvoke({"symbol": "AAPL"})
    assert "range_position: above_range" in out
    assert "STALE FIB SWING" not in out


@pytest.mark.asyncio
async def test_below_range_emits_warning() -> None:
    tool = _build_tool(current_price=85.0, low=100.0, high=150.0)
    out = await tool.ainvoke({"symbol": "TSLA"})
    assert "range_position: below_range" in out
    assert "STALE FIB SWING" in out


@pytest.mark.asyncio
async def test_aapl_reviewer_scenario() -> None:
    """Exact reviewer case: swing 277.84 → 243.42, current 288.95.

    243.42 is the low; 277.84 is the high; 288.95 is 11.5/277.84 = +4.0%
    above the high. That's borderline — currently <5% so no warning.
    Test that this borderline is honest, and that pushing to 305 (10%)
    does fire the warning.
    """
    # 4% above — borderline, no warning per the 5% threshold.
    tool = _build_tool(current_price=288.95, low=243.42, high=277.84)
    out = await tool.ainvoke({"symbol": "AAPL"})
    assert "range_position: above_range" in out
    # 4% < 5% threshold => no STALE warning
    assert "STALE FIB SWING" not in out

    # And the more extreme case: 10% above
    tool2 = _build_tool(current_price=305.6, low=243.42, high=277.84)
    out2 = await tool2.ainvoke({"symbol": "AAPL"})
    assert "STALE FIB SWING" in out2
