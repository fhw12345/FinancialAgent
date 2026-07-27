import hashlib
from types import SimpleNamespace

import pytest

from src.agent.portfolio_phase2_prompt import render_portfolio_phase2_prompt
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
    assert snapshot["consistency-gate"] == "consistency-gate@2"
    assert snapshot["portfolio-phase2"] == "portfolio-phase2@4"


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


def test_portfolio_phase2_uses_canonical_renderer():
    spec = get_prompt("portfolio-phase2")

    assert spec.renderer is render_portfolio_phase2_prompt
    rendered = render_prompt(
        "portfolio-phase2",
        symbol_analyses=[],
        total_equity=1000.0,
        buying_power=500.0,
        cash=500.0,
        positions=[],
        risk_block="RISK BLOCK\n",
        current_session="regular",
    )

    assert rendered.startswith("# Portfolio Trading Decisions")
    assert "Total Equity: $1,000.00" in rendered
    assert "| (No positions) | - | - | - | - |" in rendered
    assert "RISK BLOCK" in rendered
    assert "LANGUAGE REQUIREMENT: Respond in English." in rendered


@pytest.mark.parametrize(
    ("current_session", "expected_hash"),
    [
        (
            "regular",
            "b81eadbd1d9e6e1bb94ae43c152289af986d27722c51047f9acfa5276f088c2e",
        ),
        (
            "post",
            "d1d9d62cbea33ee2e278a5b1153b0fffa2bc9864893c02c97f65600e5c87ae7d",
        ),
    ],
)
def test_portfolio_phase2_v4_prompt_snapshot(
    current_session: str,
    expected_hash: str,
) -> None:
    rendered = render_prompt(
        "portfolio-phase2",
        symbol_analyses=[
            SimpleNamespace(
                symbol="AAPL",
                analysis_type="holding",
                analysis_text="Research line [FH-Q-AAPL-2026-05-09]",
            )
        ],
        total_equity=12345.67,
        buying_power=2345.67,
        cash=456.78,
        positions=[
            {
                "symbol": "AAPL",
                "quantity": 12,
                "market_value": 2400.5,
                "unrealized_pl_percent": 3.25,
                "session": "post",
            }
        ],
        risk_block="RISK BLOCK\n",
        current_session=current_session,
    )

    assert hashlib.sha256(rendered.encode()).hexdigest() == expected_hash
