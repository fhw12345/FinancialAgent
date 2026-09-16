"""The retired language-specific fallback must never make evidence-free LLM calls."""

from unittest.mock import patch
import pytest
from src.agent.portfolio.flows import _phase2_for_symbols


@pytest.mark.asyncio
async def test_evidence_free_fallback_is_disabled():
    with patch("src.agent.llm_factory.get_llm") as llm:
        with pytest.raises(RuntimeError, match="disabled"):
            await _phase2_for_symbols(
                symbols=["AAPL"], context={}, settings=None, flow_label="holdings"
            )
    llm.assert_not_called()
