import pytest

from src.agent.prompt_registry import (
    get_prompt,
    prompt_registry_snapshot,
    render_prompt,
)


def test_registry_has_stable_versioned_prompt_ids():
    snapshot = prompt_registry_snapshot()
    assert snapshot["router"] == "router@1"
    assert snapshot["financial-system"] == "financial-system@3"
    assert snapshot["symbol-extraction"] == "symbol-extraction@2"


def test_router_prompt_renders_context_and_unknown_prompt_fails():
    rendered = render_prompt(
        "router",
        current_symbol="AAPL",
        message="Analyze it",
    )
    assert "AAPL" in rendered
    assert "Analyze it" in rendered
    assert "Current Date: 2026-07-21" in render_prompt(
        "financial-system",
        current_date="2026-07-21",
        six_months_ago="2026-01-22",
    )
    with pytest.raises(KeyError):
        get_prompt("missing")
