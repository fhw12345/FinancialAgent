from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agent.portfolio import phase2_decisions
from src.agent.portfolio.phase2_decisions import Phase2DecisionsMixin
from src.agent.portfolio_phase2_prompt import GovernedPortfolioDecisionList
from src.models.trading_decision import SymbolAnalysisResult
from src.services import market_data


@pytest.mark.asyncio
async def test_phase2_renders_registry_prompt_and_attaches_version_after_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_result = GovernedPortfolioDecisionList(
        decisions=[],
        portfolio_assessment="No changes.",
    )
    captured_prompt = ""

    async def invoke_structured(**kwargs):
        nonlocal captured_prompt
        assert decision_result.prompt_versions == {}
        captured_prompt = kwargs["prompt"]
        return decision_result

    stub = MagicMock()
    stub._fetch_symbol_meta_for_risk = AsyncMock(return_value={})
    stub._fetch_symbol_returns_for_risk = AsyncMock(return_value=[])
    stub.react_agent.ainvoke_structured = AsyncMock(side_effect=invoke_structured)

    monkeypatch.setattr(
        phase2_decisions,
        "compute_portfolio_risk",
        AsyncMock(return_value=object()),
    )
    monkeypatch.setattr(
        phase2_decisions,
        "render_risk_block_for_prompt",
        lambda _risk: "RISK BLOCK\n",
    )
    get_market_session = MagicMock(return_value="regular")
    monkeypatch.setattr(market_data, "get_market_session", get_market_session)

    analysis = SymbolAnalysisResult(
        symbol="AAPL",
        analysis_type="holding",
        analysis_text="Quote $200 [FH-Q-AAPL-2026-07-27]",
        analysis_id="analysis",
        chat_id="chat",
    )
    result = await Phase2DecisionsMixin._make_portfolio_decisions(
        stub,
        symbol_analyses=[analysis],
        portfolio_context={
            "total_equity": 1000.0,
            "buying_power": 500.0,
            "cash": 500.0,
            "positions": [],
        },
        user_id="test",
    )

    assert result is decision_result
    assert result.prompt_versions == {
        "portfolio-phase2": "portfolio-phase2@4",
    }
    assert "# Portfolio Trading Decisions" in captured_prompt
    assert "Quote $200 [FH-Q-AAPL-2026-07-27]" in captured_prompt
    get_market_session.assert_called_once()
    stub.react_agent.ainvoke_structured.assert_awaited_once()


@pytest.mark.asyncio
async def test_phase2_without_analyses_does_not_execute_or_attach_version() -> None:
    stub = MagicMock()
    stub.react_agent.ainvoke_structured = AsyncMock()

    result = await Phase2DecisionsMixin._make_portfolio_decisions(
        stub,
        symbol_analyses=[],
        portfolio_context={},
        user_id="test",
    )

    assert result is None
    stub.react_agent.ainvoke_structured.assert_not_awaited()
