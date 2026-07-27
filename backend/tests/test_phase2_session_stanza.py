"""Snapshot-style test that the Phase 2 prompt renderer grows a session
warning stanza when current US/Eastern session is not 'regular'.

Calling the renderer avoids booting the LangGraph agent + LLM + repos.
We assert by source-inspection that:
  1. The stanza string is built from `current_session` correctly
  2. The canonical prompt injects `{session_stanza}` between
     `{positions_table}` and `## Symbol Research Results`

This catches regressions where someone removes the injection or breaks the
session→label mapping, without needing a live LLM.
"""

import inspect
import re

import pytest

from src.agent import portfolio_phase2_prompt
from src.services.market_data import get_market_session


def _source_of_prompt_module() -> str:
    return inspect.getsource(portfolio_phase2_prompt)


def _source_of_prompt_renderer() -> str:
    return inspect.getsource(portfolio_phase2_prompt.render_portfolio_phase2_prompt)


def test_module_imports_and_helper_resolves() -> None:
    # Trips immediately if the session helper moves or its imports break.
    assert callable(get_market_session)


def test_prompt_source_references_session_stanza() -> None:
    src = _source_of_prompt_renderer()
    # The variable + injection both have to exist
    assert "session_stanza" in src
    assert "{session_stanza}" in src


def test_prompt_source_branches_on_current_session() -> None:
    prompt_src = _source_of_prompt_module()
    assert 'current_session == "regular"' in prompt_src


@pytest.mark.parametrize(
    "session_label",
    [
        "盘前",
        "盘后",
        "休市",
    ],
)
def test_all_non_regular_labels_present(session_label: str) -> None:
    src = _source_of_prompt_module()
    assert session_label in src, f"missing session label: {session_label}"


def test_stanza_appears_between_holdings_and_research() -> None:
    """`session_stanza` must be injected after the holdings table and
    before the symbol research section, so the LLM sees the warning before
    it starts reasoning about prices."""
    src = _source_of_prompt_renderer()
    # Find positions of the markers
    pos_table = src.find("{positions_table}")
    stanza = src.find("{session_stanza}")
    research = src.find("## Symbol Research Results")
    assert pos_table != -1
    assert stanza != -1
    assert research != -1
    assert (
        pos_table < stanza < research
    ), "session_stanza must be between positions_table and Symbol Research"


def test_warning_does_not_block_decision() -> None:
    """Per design: warn-not-block. Source must say so explicitly."""
    src = _source_of_prompt_module()
    assert re.search(
        r"不强制阻断决策|不阻断", src
    ), "stanza must explicitly say it does not block the decision"
