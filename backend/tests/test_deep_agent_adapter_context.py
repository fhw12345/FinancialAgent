"""Tests for DeepAgentAdapter context forwarding and symbol continuity."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agent.deep_agent_adapter import DeepAgentAdapter
from src.models.symbol_resolution import SymbolCandidate, SymbolResolution


@pytest.mark.asyncio
async def test_adapter_forwards_structured_research_context():
    deep_agent = SimpleNamespace(
        analyze=AsyncMock(
            return_value={
                "research_report": "Follow-up verdict",
                "messages": [],
                "round_count": 1,
            }
        )
    )
    resolver = SimpleNamespace(
        resolve=AsyncMock(
            return_value=SymbolResolution(
                status="resolved",
                source="ui_context",
                reason_code="resolved_ui_symbol",
                symbol="SKHY",
                company_name="SK hynix",
                confidence=1.0,
                candidates=[
                    SymbolCandidate(
                        symbol="SKHY",
                        name="SK hynix",
                        confidence=1.0,
                    )
                ],
            )
        )
    )
    adapter = DeepAgentAdapter(deep_agent, resolver)

    result = await adapter.ainvoke(
        user_message="Now challenge that thesis.",
        conversation_history=[
            {
                "role": "user",
                "content": "Analyze SKHY over 6 months with moderate risk.",
            },
            {
                "role": "assistant",
                "content": "The prior SKHY thesis was bullish.",
            },
        ],
        current_symbol="SKHY",
    )

    research_context = deep_agent.analyze.await_args.kwargs["research_context"]
    assert research_context.confirmed_symbol == "SKHY"
    assert research_context.investment_horizon == "6 months"
    assert research_context.risk_tolerance == "moderate"
    assert "bullish" in research_context.previous_assistant_report
    assert result["research_context"]["has_previous_report"] is True


@pytest.mark.asyncio
async def test_adapter_preserves_request_local_prompt_versions_on_failure():
    async def fail_after_prompt(on_event, **kwargs):
        on_event(
            {
                "type": "prompt_used",
                "prompt_id": "deep-debater",
                "version": "deep-debater@3",
            }
        )
        raise RuntimeError("invalid structured debate output")

    deep_agent = SimpleNamespace(analyze=AsyncMock(side_effect=fail_after_prompt))
    resolver = SimpleNamespace(
        resolve=AsyncMock(
            return_value=SymbolResolution(
                status="resolved",
                source="explicit_ticker",
                reason_code="resolved_explicit_ticker",
                symbol="AAPL",
                confidence=1.0,
            )
        )
    )
    adapter = DeepAgentAdapter(deep_agent, resolver)

    result = await adapter.ainvoke(
        user_message="Deeply analyze AAPL.",
        resolved_symbol="AAPL",
    )

    assert result["error"] == "invalid structured debate output"
    assert result["prompt_versions"] == {"deep-debater": "deep-debater@3"}


@pytest.mark.asyncio
async def test_adapter_clears_target_specific_history_after_symbol_switch():
    deep_agent = SimpleNamespace(
        analyze=AsyncMock(
            return_value={
                "research_report": "MSFT verdict",
                "messages": [],
                "round_count": 1,
            }
        )
    )
    resolver = SimpleNamespace(
        resolve=AsyncMock(
            return_value=SymbolResolution(
                status="resolved",
                source="explicit_ticker",
                reason_code="resolved_explicit_ticker",
                symbol="MSFT",
                company_name="Microsoft",
                confidence=1.0,
                candidates=[
                    SymbolCandidate(
                        symbol="MSFT",
                        name="Microsoft",
                        confidence=1.0,
                    )
                ],
            )
        )
    )
    adapter = DeepAgentAdapter(deep_agent, resolver)

    await adapter.ainvoke(
        user_message="Analyze MSFT.",
        conversation_history=[
            {
                "role": "user",
                "content": "Analyze AAPL over 6 months using valuation only.",
            },
            {"role": "assistant", "content": "The AAPL thesis is bullish."},
        ],
        current_symbol="AAPL",
    )

    context = deep_agent.analyze.await_args.kwargs["research_context"]
    assert context.previous_assistant_report is None
    assert context.investment_horizon is None
    assert context.constraints == ()


@pytest.mark.asyncio
async def test_adapter_clears_unidentified_history_target():
    deep_agent = SimpleNamespace(
        analyze=AsyncMock(
            return_value={
                "research_report": "MSFT verdict",
                "messages": [],
                "round_count": 1,
            }
        )
    )
    resolver = SimpleNamespace(
        resolve=AsyncMock(
            return_value=SymbolResolution(
                status="resolved",
                source="local_directory",
                reason_code="resolved_ranked_search",
                symbol="MSFT",
                company_name="Microsoft",
                confidence=0.95,
                candidates=[
                    SymbolCandidate(
                        symbol="MSFT",
                        name="Microsoft",
                        confidence=0.95,
                    )
                ],
            )
        )
    )
    adapter = DeepAgentAdapter(deep_agent, resolver)

    await adapter.ainvoke(
        user_message="Analyze Microsoft.",
        conversation_history=[
            {"role": "user", "content": "Analyze Apple."},
            {"role": "assistant", "content": "The prior thesis is bullish."},
        ],
    )

    context = deep_agent.analyze.await_args.kwargs["research_context"]
    assert context.previous_user_request is None
    assert context.previous_assistant_report is None


@pytest.mark.asyncio
async def test_adapter_follow_up_uses_only_latest_symbol_segment():
    deep_agent = SimpleNamespace(
        analyze=AsyncMock(
            return_value={
                "research_report": "MSFT follow-up",
                "messages": [],
                "round_count": 1,
            }
        )
    )
    resolver = SimpleNamespace(
        resolve=AsyncMock(
            return_value=SymbolResolution(
                status="resolved",
                source="ui_context",
                reason_code="resolved_ui_symbol",
                symbol="MSFT",
                company_name="Microsoft",
                confidence=1.0,
                candidates=[
                    SymbolCandidate(
                        symbol="MSFT",
                        name="Microsoft",
                        confidence=1.0,
                    )
                ],
            )
        )
    )
    adapter = DeepAgentAdapter(deep_agent, resolver)

    await adapter.ainvoke(
        user_message="Continue that thesis.",
        conversation_history=[
            {
                "role": "user",
                "content": (
                    "Analyze AAPL over 6 months with conservative risk and "
                    "valuation only."
                ),
            },
            {"role": "assistant", "content": "The AAPL thesis is bullish."},
            {"role": "user", "content": "Analyze Microsoft instead."},
            {"role": "assistant", "content": "The MSFT thesis is neutral."},
        ],
        current_symbol="MSFT",
    )

    context = deep_agent.analyze.await_args.kwargs["research_context"]
    assert context.previous_assistant_report == "The MSFT thesis is neutral."
    assert context.investment_horizon is None
    assert context.risk_tolerance is None
    assert context.constraints == ()


@pytest.mark.asyncio
async def test_follow_up_can_reuse_validated_prior_symbol():
    prior_symbol = SymbolResolution(
        status="resolved",
        source="ui_context",
        reason_code="resolved_ui_symbol",
        symbol="SKHY",
        company_name="SK hynix",
        confidence=1.0,
        candidates=[SymbolCandidate(symbol="SKHY", name="SK hynix", confidence=1.0)],
    )
    resolver = SimpleNamespace(
        resolve=AsyncMock(
            side_effect=[
                SymbolResolution(
                    status="unresolved",
                    source="llm_assisted",
                    reason_code="symbol_missing",
                ),
                prior_symbol,
            ]
        )
    )
    adapter = DeepAgentAdapter(SimpleNamespace(), resolver)

    result = await adapter.resolve_symbol(
        user_message="Continue and challenge that thesis.",
        current_symbol=None,
        conversation_history=[
            {"role": "assistant", "content": "Previous SKHY verdict was HOLD."},
        ],
    )

    assert result.symbol == "SKHY"
    assert resolver.resolve.await_count == 2
    assert resolver.resolve.await_args.kwargs == {
        "message": "SKHY",
        "current_symbol": None,
    }


@pytest.mark.asyncio
async def test_follow_up_skips_invalid_latest_historical_candidate():
    missing = SymbolResolution(
        status="unresolved",
        source="local_directory",
        reason_code="symbol_missing",
    )
    invalid = SymbolResolution(
        status="unresolved",
        source="explicit_ticker",
        reason_code="symbol_not_found",
    )
    prior_symbol = SymbolResolution(
        status="resolved",
        source="explicit_ticker",
        reason_code="resolved_explicit_ticker",
        symbol="AAPL",
        company_name="Apple",
        confidence=1.0,
        candidates=[SymbolCandidate(symbol="AAPL", name="Apple", confidence=1.0)],
    )
    resolver = SimpleNamespace(
        resolve=AsyncMock(side_effect=[missing, invalid, prior_symbol])
    )
    adapter = DeepAgentAdapter(SimpleNamespace(), resolver)

    result = await adapter.resolve_symbol(
        user_message="Continue that comparison.",
        current_symbol=None,
        conversation_history=[
            {
                "role": "user",
                "content": "Compare AAPL with ZZZZZ and continue with ZZZZZ.",
            },
        ],
    )

    assert result.symbol == "AAPL"
    assert [call.kwargs["message"] for call in resolver.resolve.await_args_list] == [
        "Continue that comparison.",
        "ZZZZZ",
        "AAPL",
    ]


@pytest.mark.asyncio
async def test_follow_up_with_multiple_valid_history_symbols_is_ambiguous():
    missing = SymbolResolution(
        status="unresolved",
        source="local_directory",
        reason_code="symbol_missing",
    )
    aapl = SymbolResolution(
        status="resolved",
        source="explicit_ticker",
        reason_code="resolved_explicit_ticker",
        symbol="AAPL",
        company_name="Apple",
        confidence=1.0,
        candidates=[SymbolCandidate(symbol="AAPL", name="Apple", confidence=1.0)],
    )
    msft = SymbolResolution(
        status="resolved",
        source="explicit_ticker",
        reason_code="resolved_explicit_ticker",
        symbol="MSFT",
        company_name="Microsoft",
        confidence=1.0,
        candidates=[SymbolCandidate(symbol="MSFT", name="Microsoft", confidence=1.0)],
    )
    resolver = SimpleNamespace(resolve=AsyncMock(side_effect=[missing, msft, aapl]))
    adapter = DeepAgentAdapter(SimpleNamespace(), resolver)

    result = await adapter.resolve_symbol(
        user_message="Continue that comparison.",
        current_symbol=None,
        conversation_history=[
            {"role": "user", "content": "Compare AAPL and MSFT."},
        ],
    )

    assert result.status == "ambiguous"
    assert [candidate.symbol for candidate in result.candidates] == ["MSFT", "AAPL"]


@pytest.mark.asyncio
async def test_non_follow_up_does_not_reuse_history_symbol():
    unresolved = SymbolResolution(
        status="unresolved",
        source="llm_assisted",
        reason_code="symbol_missing",
    )
    resolver = SimpleNamespace(resolve=AsyncMock(return_value=unresolved))
    adapter = DeepAgentAdapter(SimpleNamespace(), resolver)

    result = await adapter.resolve_symbol(
        user_message="Analyze a different company.",
        current_symbol=None,
        conversation_history=[
            {"role": "assistant", "content": "Previous SKHY verdict was HOLD."},
        ],
    )

    assert result.status == "unresolved"
    resolver.resolve.assert_awaited_once()


@pytest.mark.asyncio
async def test_explicit_invalid_symbol_does_not_fall_back_to_history():
    unresolved = SymbolResolution(
        status="unresolved",
        source="explicit_ticker",
        reason_code="symbol_not_found",
    )
    resolver = SimpleNamespace(resolve=AsyncMock(return_value=unresolved))
    adapter = DeepAgentAdapter(SimpleNamespace(), resolver)

    result = await adapter.resolve_symbol(
        user_message="Continue with ZZZZZ.",
        current_symbol=None,
        conversation_history=[
            {"role": "assistant", "content": "Previous AAPL verdict was HOLD."},
        ],
    )

    assert result.reason_code == "symbol_not_found"
    resolver.resolve.assert_awaited_once()
