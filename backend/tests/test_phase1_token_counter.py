"""W3.16-C unit tests — Phase 1 reads top-level token counts from ReAct response.

The Phase 1 research path is the only place we record per-symbol token
cost. Before W3.16-C the extraction was

    usage = response.get("usage", {})
    input_tokens = usage.get("input_tokens", 0)

…but ``react_agent.ainvoke`` (langgraph_react_agent.py:1042-1049) returns
the dict shape::

    {
      "trace_id": ...,
      "messages": [...],
      "final_answer": "...",
      "tool_executions": 5,
      "input_tokens": 1234,
      "output_tokens": 567,
      ...
    }

There is NO ``"usage"`` wrapper, so the old extraction always produced
0/0 — observed live on 2026-05-09 in NVDA single_symbol flow logs::

    Phase 1: Symbol research completed input_tokens=0 output_tokens=0

These tests pin the new shape so a future refactor that re-introduces
the wrapper would break loudly.

Implementation note: ``phase1_research`` uses ``structlog`` whose
``logger.info`` does NOT propagate through stdlib ``logging``, so
``caplog`` cannot see kwargs. We patch ``phase1_research.logger.info``
with a recording stub instead and assert against the captured kwargs.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agent.portfolio import phase1_research
from src.agent.portfolio.phase1_research import Phase1ResearchMixin


def _build_mixin_with_response(response: object) -> Phase1ResearchMixin:
    """Construct a bare Phase1ResearchMixin instance and stub ONLY the
    attributes ``_analyze_symbol`` actually touches in the
    ``suppress_chat=True`` branch (avoids constructing the full agent /
    Mongo / Redis stack just to test arithmetic)."""
    mixin = Phase1ResearchMixin.__new__(Phase1ResearchMixin)
    mixin.react_agent = SimpleNamespace(ainvoke=AsyncMock(return_value=response))
    mixin.context_manager = SimpleNamespace()
    mixin.settings = SimpleNamespace(dashscope_model="qwen-plus")
    mixin.message_repo = SimpleNamespace()
    mixin.chat_repo = SimpleNamespace()
    return mixin


@pytest.fixture
def captured_logs(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict]]:
    """Replace the structlog logger.info bound name in phase1_research
    with a recording stub. Returns a list[(event_name, kwargs)] the test
    can introspect."""
    captured: list[tuple[str, dict]] = []

    def _record(event: str, **kwargs: object) -> None:
        captured.append((event, dict(kwargs)))

    # logger.info / .warning / .error all share the same module-level
    # logger; patch the whole logger so nothing slips through.
    fake = SimpleNamespace(
        info=_record,
        warning=_record,
        error=_record,
        debug=_record,
    )
    monkeypatch.setattr(phase1_research, "logger", fake)
    return captured


def _completion_kwargs(captured: list[tuple[str, dict]]) -> dict:
    matches = [
        kw for event, kw in captured if event == "Phase 1: Symbol research completed"
    ]
    assert matches, f"expected the completion log event; saw {[e for e, _ in captured]}"
    return matches[0]


@pytest.mark.asyncio
async def test_phase1_extracts_top_level_token_counts(
    captured_logs: list[tuple[str, dict]],
) -> None:
    """The fix: when the ReAct response carries top-level
    ``input_tokens`` / ``output_tokens`` the structlog ``Phase 1: Symbol
    research completed`` event must carry the same numbers — not 0/0."""
    response = {
        "trace_id": "test-trace",
        "messages": [],
        "final_answer": "## NVDA Research\n\n**Price:** $215.20",
        "tool_executions": 4,
        "input_tokens": 1234,
        "output_tokens": 567,
        "total_tokens": 1801,
    }
    mixin = _build_mixin_with_response(response)

    result = await mixin._analyze_symbol(
        symbol="NVDA",
        user_id="portfolio_agent",
        analysis_type="watchlist",
        suppress_chat=True,
    )

    assert result is not None
    assert result.symbol == "NVDA"
    kw = _completion_kwargs(captured_logs)
    assert kw.get("input_tokens") == 1234
    assert kw.get("output_tokens") == 567


@pytest.mark.asyncio
async def test_phase1_legacy_usage_wrapper_no_longer_supported(
    captured_logs: list[tuple[str, dict]],
) -> None:
    """If the response *only* carries the old ``{"usage": {...}}`` shape
    we DO read 0/0 — that's the deliberate failure mode that catches a
    future regression where the ReAct agent silently changes its return
    contract back to the wrapped form."""
    response = {
        "trace_id": "legacy",
        "messages": [],
        "final_answer": "## body",
        "usage": {"input_tokens": 999, "output_tokens": 999},
    }
    mixin = _build_mixin_with_response(response)
    await mixin._analyze_symbol(
        symbol="NVDA",
        user_id="portfolio_agent",
        analysis_type="watchlist",
        suppress_chat=True,
    )
    kw = _completion_kwargs(captured_logs)
    assert kw.get("input_tokens") == 0
    assert kw.get("output_tokens") == 0


@pytest.mark.asyncio
async def test_phase1_handles_missing_token_keys(
    captured_logs: list[tuple[str, dict]],
) -> None:
    """A response dict that is missing both keys (e.g. an early-error
    short-circuit) must default to 0/0 without raising."""
    response = {
        "trace_id": "early-exit",
        "messages": [],
        "final_answer": "",
        "tool_executions": 0,
    }
    mixin = _build_mixin_with_response(response)
    result = await mixin._analyze_symbol(
        symbol="NVDA",
        user_id="portfolio_agent",
        analysis_type="watchlist",
        suppress_chat=True,
    )
    assert result is not None
    kw = _completion_kwargs(captured_logs)
    assert kw.get("input_tokens") == 0
    assert kw.get("output_tokens") == 0


@pytest.mark.asyncio
async def test_phase1_handles_none_token_value(
    captured_logs: list[tuple[str, dict]],
) -> None:
    """``None`` shows up when the LLM gateway didn't echo usage back —
    the ``or 0`` guard in the fix should coerce it without raising."""
    response = {
        "trace_id": "null-tokens",
        "messages": [],
        "final_answer": "ok",
        "tool_executions": 1,
        "input_tokens": None,
        "output_tokens": None,
    }
    mixin = _build_mixin_with_response(response)
    await mixin._analyze_symbol(
        symbol="NVDA",
        user_id="portfolio_agent",
        analysis_type="watchlist",
        suppress_chat=True,
    )
    kw = _completion_kwargs(captured_logs)
    assert kw.get("input_tokens") == 0
    assert kw.get("output_tokens") == 0

