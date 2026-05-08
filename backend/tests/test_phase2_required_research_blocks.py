"""Source-inspection test for bug #1 fix: the Phase 2 decision prompt
must require W2.7+ structured research blocks (thesis / valuation /
scenarios / catalysts / risks) on every BUY/SELL decision instead of
framing them as optional.

Symptom that drove this fix: 76/76 production decisions had
thesis = valuation = scenarios = null, because the original prompt
called these fields **optional for back-compat** and warned that
validators would reject malformed blocks. The LLM minimized risk by
emitting null on every block.

This test guards against regressing back to the optional framing.
"""

import inspect

from src.agent.portfolio import phase2_decisions


def _src() -> str:
    return inspect.getsource(
        phase2_decisions.Phase2DecisionsMixin._make_portfolio_decisions
    )


def test_prompt_marks_blocks_required_for_buy_sell() -> None:
    src = _src()
    assert "REQUIRED for BUY/SELL" in src, (
        "prompt must explicitly mark structured research blocks REQUIRED"
    )


def test_prompt_does_not_call_blocks_optional() -> None:
    """The old prompt said 'optional for back-compat with older runs'.
    Bug #1 root cause was exactly that wording — keep it gone."""
    src = _src()
    assert "optional for back-compat" not in src, (
        "old optional framing returned; LLM will go back to emitting null"
    )
    assert "Optional Structured Research Blocks" not in src, (
        "old section header returned"
    )


def test_prompt_lists_all_w27_block_names() -> None:
    src = _src()
    for name in ("thesis", "valuation", "price_target", "scenarios", "catalysts", "risks"):
        assert f"`{name}`" in src, f"prompt does not document `{name}` block"


def test_prompt_includes_worked_buy_example() -> None:
    """The fix adds a worked example with all blocks populated so the
    LLM has a concrete schema target instead of free-text guidance."""
    src = _src()
    assert "Worked example" in src
    # Spot-check that the example actually shows the keys, not just names them
    for key in ('"thesis":', '"valuation":', '"scenarios":', '"catalysts":', '"risks":'):
        assert key in src, f"worked example missing key: {key}"


def test_prompt_says_downgrade_to_hold_if_data_missing() -> None:
    """The escape hatch must be downgrade-to-HOLD, not emit-null-BUY."""
    src = _src()
    assert "downgrade the decision to HOLD" in src.lower() or "downgrade" in src


def test_prompt_actually_builds_without_format_error() -> None:
    """Regression: the worked-example block contains JSON with `{` `}`,
    which Python f-string treats as substitution. The braces inside the
    example must be escaped (`{{` / `}}`) so building the prompt does
    not raise ValueError: Invalid format specifier.

    Catches a real production regression: shipping unescaped braces
    surfaced at runtime as `ValueError: Invalid format specifier` and
    crashed the holdings flow.
    """
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from src.agent.portfolio.phase2_decisions import Phase2DecisionsMixin
    from src.models.trading_decision import SymbolAnalysisResult

    stub = MagicMock()
    stub._fetch_symbol_meta_for_risk = AsyncMock(return_value={})
    stub._fetch_symbol_returns_for_risk = AsyncMock(return_value=[])
    stub.react_agent = MagicMock()
    stub.react_agent.ainvoke_structured = AsyncMock(
        side_effect=RuntimeError("stop after prompt build")
    )

    sar = SymbolAnalysisResult(
        symbol="TEST",
        analysis_type="watchlist",
        analysis_text="dummy",
        analysis_id="t",
        chat_id="t",
    )

    async def _run() -> None:
        await Phase2DecisionsMixin._make_portfolio_decisions(
            stub,
            symbol_analyses=[sar],
            portfolio_context={
                "total_equity": 1000.0,
                "buying_power": 500.0,
                "cash": 500.0,
                "positions": [],
            },
            user_id="test",
        )

    try:
        asyncio.run(_run())
    except RuntimeError as e:
        # Reached the LLM call → f-string built fine.
        assert "stop after prompt build" in str(e), f"unexpected RuntimeError: {e}"
    except ValueError as e:
        if "format specifier" in str(e):
            raise AssertionError(
                f"prompt f-string has unescaped braces: {e}"
            ) from e
        raise
