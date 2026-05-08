"""W1.10 unit tests — consistency gate detection + hint rendering.

The LLM-call path is exercised via mocked structured output to avoid
network calls in CI; the deterministic regex helpers get full coverage.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.portfolio.consistency_gate import (
    GateVerdict,
    GateViolation,
    detect_degraded_fields,
    run_consistency_gate,
    violations_as_corrective_hint,
)

# ---------------------------------------------------------------------------
# detect_degraded_fields (regex)
# ---------------------------------------------------------------------------


class TestDetectDegradedFields:
    def test_clean_research_returns_empty(self) -> None:
        assert detect_degraded_fields("RSI 55, MACD bullish, P/E 18.2.") == []

    def test_unavailable_message_detected(self) -> None:
        text = (
            "## Fundamentals\n"
            "⚠️ **Cash flow unavailable for CRWV.** Alpha Vantage error: "
            "rate limited. Treat any downstream claim as unsubstantiated."
        )
        out = detect_degraded_fields(text)
        assert len(out) == 1
        assert "Cash flow" in out[0]
        assert "CRWV" in out[0]

    def test_multiple_unavailable_fields(self) -> None:
        text = (
            "⚠️ **Company overview unavailable for AAPL.** unsubstantiated.\n"
            "⚠️ **Earnings unavailable for AAPL.** unsubstantiated."
        )
        out = detect_degraded_fields(text)
        assert len(out) == 2

    def test_stale_fib_warning_detected(self) -> None:
        text = (
            "Fibonacci: AAPL\n"
            "range_position: above_range\n"
            "⚠️ STALE FIB SWING: current $290 is 9% above the $244-$278 range."
        )
        out = detect_degraded_fields(text)
        assert any("Fibonacci" in d for d in out)
        assert any("above_range" in d for d in out)

    def test_in_range_no_warning_treated_as_clean(self) -> None:
        text = "Fibonacci: AAPL\nrange_position: in_range\nGolden zone $264."
        # in_range alone does NOT have the STALE banner → no signal
        assert detect_degraded_fields(text) == []

    def test_combined_unavailable_and_stale(self) -> None:
        text = (
            "⚠️ **Cash flow unavailable for AAPL.** unsubstantiated.\n"
            "STALE FIB SWING: ...\nrange_position: below_range"
        )
        out = detect_degraded_fields(text)
        assert len(out) == 2


# ---------------------------------------------------------------------------
# run_consistency_gate (LLM-mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gate_skips_llm_when_no_degraded() -> None:
    text = "Clean RSI 55. P/E 18."
    with patch("src.agent.portfolio.consistency_gate.get_llm") as mock_llm:
        verdict, degraded = await run_consistency_gate("AAPL", text)
    assert verdict.passed is True
    assert verdict.violations == []
    assert degraded == []
    # Cost discipline: do NOT call the LLM when nothing to check.
    mock_llm.assert_not_called()


@pytest.mark.asyncio
async def test_gate_calls_llm_when_degraded_present() -> None:
    text = (
        "## Bullish thesis\n- AAPL is the cheapest of the cohort\n\n"
        "## Fundamentals\n⚠️ **Cash flow unavailable for AAPL.** "
        "unsubstantiated."
    )
    fake_llm = MagicMock()
    fake_structured = MagicMock()
    fake_structured.ainvoke = AsyncMock(
        return_value=GateVerdict(
            passed=False,
            violations=[
                GateViolation(
                    field="Cash flow unavailable for AAPL",
                    quote="AAPL is the cheapest of the cohort",
                )
            ],
        )
    )
    fake_llm.with_structured_output = MagicMock(return_value=fake_structured)
    with patch(
        "src.agent.portfolio.consistency_gate.get_llm",
        return_value=fake_llm,
    ):
        verdict, degraded = await run_consistency_gate("AAPL", text)
    assert verdict.passed is False
    assert len(verdict.violations) == 1
    assert len(degraded) == 1


@pytest.mark.asyncio
async def test_gate_fails_open_on_llm_exception() -> None:
    text = "⚠️ **Cash flow unavailable for AAPL.** unsubstantiated."
    fake_llm = MagicMock()
    fake_structured = MagicMock()
    fake_structured.ainvoke = AsyncMock(side_effect=RuntimeError("network"))
    fake_llm.with_structured_output = MagicMock(return_value=fake_structured)
    with patch(
        "src.agent.portfolio.consistency_gate.get_llm",
        return_value=fake_llm,
    ):
        verdict, degraded = await run_consistency_gate("AAPL", text)
    # Fail-open so a flaky gate doesn't wedge the pipeline.
    assert verdict.passed is True
    assert "failed-open" in (verdict.note or "")
    assert len(degraded) == 1


# ---------------------------------------------------------------------------
# violations_as_corrective_hint
# ---------------------------------------------------------------------------


def test_hint_empty_when_no_violations() -> None:
    assert violations_as_corrective_hint([]) == ""


def test_hint_includes_quote_and_field() -> None:
    v = [
        GateViolation(
            field="P/E unavailable for AAPL",
            quote="cheapest of seven",
        )
    ]
    hint = violations_as_corrective_hint(v)
    assert "cheapest of seven" in hint
    assert "P/E unavailable" in hint
    assert "MUST fix" in hint
    assert "Rewrite" in hint
