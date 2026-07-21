import pytest

from src.agent.prompt_registry import (
    get_prompt,
    prompt_registry_snapshot,
    render_prompt,
)


def test_registry_has_stable_versioned_prompt_ids():
    snapshot = prompt_registry_snapshot()
    assert snapshot["router"] == "router@1"
    assert snapshot == {"router": "router@1"}


def test_router_prompt_renders_context_and_unknown_prompt_fails():
    rendered = render_prompt(
        "router",
        current_symbol="AAPL",
        message="Analyze it",
    )
    assert "AAPL" in rendered
    assert "Analyze it" in rendered
    with pytest.raises(KeyError):
        get_prompt("missing")
