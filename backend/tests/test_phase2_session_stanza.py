"""Snapshot-style test that the Phase 2 prompt builder grows a session
warning stanza when current US/Eastern session is not 'regular'.

Calling `_make_portfolio_decisions` directly would require booting the
LangGraph agent + LLM + repos. Instead we assert by source-inspection that:
  1. The stanza string is built from `current_session` correctly
  2. The decision_prompt template injects `{session_stanza}` between
     `{positions_table}` and `## Symbol Research Results`

This catches regressions where someone removes the injection or breaks the
session→label mapping, without needing a live LLM.
"""

import inspect
import re

import pytest

from src.agent.portfolio import phase2_decisions
from src.services.market_data import get_market_session


def _source_of_make_decisions() -> str:
    """Pull the source of the method that builds the prompt."""
    return inspect.getsource(
        phase2_decisions.Phase2DecisionsMixin._make_portfolio_decisions
    )


def test_module_imports_and_helper_resolves() -> None:
    # Trips immediately if the get_market_session import in phase2_decisions.py
    # ever breaks (e.g. circular import after a future refactor).
    assert callable(get_market_session)


def test_prompt_source_references_session_stanza() -> None:
    src = _source_of_make_decisions()
    # The variable + injection both have to exist
    assert "session_stanza" in src
    assert "{session_stanza}" in src


def test_prompt_source_branches_on_current_session() -> None:
    src = _source_of_make_decisions()
    # Must call get_market_session and branch on regular
    assert "get_market_session" in src
    assert 'current_session == "regular"' in src


@pytest.mark.parametrize(
    "session_label",
    [
        "盘前",
        "盘后",
        "休市",
    ],
)
def test_all_non_regular_labels_present(session_label: str) -> None:
    src = _source_of_make_decisions()
    assert session_label in src, f"missing session label: {session_label}"


def test_stanza_appears_between_holdings_and_research() -> None:
    """`session_stanza` must be injected after the holdings table and
    before the symbol research section, so the LLM sees the warning before
    it starts reasoning about prices."""
    src = _source_of_make_decisions()
    # Find positions of the markers
    pos_table = src.find("{positions_table}")
    stanza = src.find("{session_stanza}")
    research = src.find("## Symbol Research Results")
    assert pos_table != -1
    assert stanza != -1
    assert research != -1
    assert pos_table < stanza < research, (
        "session_stanza must be between positions_table and Symbol Research"
    )


def test_warning_does_not_block_decision() -> None:
    """Per design: warn-not-block. Source must say so explicitly."""
    src = _source_of_make_decisions()
    assert re.search(r"不强制阻断决策|不阻断", src), (
        "stanza must explicitly say it does not block the decision"
    )
