"""Capture the prompt actually delivered to the Phase 1 agent boundary."""

import asyncio
from functools import lru_cache
from types import SimpleNamespace
from unittest.mock import AsyncMock
from src.agent.portfolio.phase1_research import Phase1ResearchMixin


@lru_cache(maxsize=1)
def phase1_prompt() -> str:
    research = Phase1ResearchMixin()
    invoke = AsyncMock(return_value={"final_answer": "Recorded research"})
    research.react_agent = SimpleNamespace(ainvoke=invoke)
    result = asyncio.run(
        research._analyze_symbol("AAPL", "local", "holding", suppress_chat=True)
    )
    assert result is not None
    invoke.assert_awaited_once()
    return invoke.call_args.args[0]
