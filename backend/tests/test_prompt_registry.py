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
    assert snapshot["deep-debater"] == "deep-debater@2"
    assert snapshot["deep-rebuttal"] == "deep-rebuttal@1"
    assert snapshot["deep-verdict"] == "deep-verdict@1"


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


def test_deep_prompt_contracts_preserve_structured_fields():
    rebuttal = render_prompt(
        "deep-rebuttal",
        research_context="context",
        symbol="AAPL",
        concern_lines="- C1",
    )
    debater = render_prompt(
        "deep-debater",
        research_context="context",
        report="report",
        termination_signal="NO_CONCERNS",
    )
    verdict = render_prompt(
        "deep-verdict",
        verified_facts="facts",
        research_context="context",
        report="report",
    )

    assert "REFUTED|PARTIALLY_VALID|CONCEDED" in rebuttal
    assert '"category": "technical|fundamental|valuation|risk"' in debater
    assert "NEEDS MORE EVIDENCE" in verdict
