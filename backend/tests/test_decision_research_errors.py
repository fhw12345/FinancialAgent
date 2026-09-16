"""An error envelope must not become research merely by stringifying it."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from src.agent.portfolio.phase1_research import Phase1ResearchMixin


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        {"error": "provider unavailable", "final_answer": "Error occurred"},
        {"unexpected": "shape"},
        {"final_answer": ""},
        None,
    ],
)
async def test_error_envelopes_and_empty_output_are_missing_research(response):
    research = Phase1ResearchMixin()
    research.react_agent = SimpleNamespace(ainvoke=AsyncMock(return_value=response))
    assert (
        await research._analyze_symbol("AAPL", "local", "holding", suppress_chat=True)
        is None
    )
    research.react_agent.ainvoke.assert_awaited_once()
