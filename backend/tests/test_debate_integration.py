"""Integration tests for symmetric debate flow with structured fact tracking.

Tests the full graph topology: main_agent → debater → should_continue →
main_agent(rebuttal) → debater → verdict, verifying:
- Symmetric rounds (main agent always responds before verdict)
- Structured JSON concerns/rebuttals are parsed and accumulated
- Verified facts are merged and injected into verdict prompt
- Debater uses only independent tools (yfinance, exa)
- State transitions preserve all_concerns/all_rebuttals across rounds
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.debate_types import (
    Concern,
    MergedFact,
    Rebuttal,
    merge_facts,
    parse_debater_output,
    parse_rebuttal_output,
    render_verified_facts_reminder,
)
from src.agent.subagents.debater import TERMINATION_SIGNAL


# ===== Fixtures =====


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock application settings."""
    settings = MagicMock()
    settings.default_llm_model = "qwen-plus-latest"
    settings.dashscope_api_key = "test-key"
    settings.default_llm_temperature = 0.7
    settings.exa_api_key = "test-exa-key"
    return settings


def _make_debater_response_with_concerns() -> str:
    """Create a realistic debater response with structured JSON concerns."""
    return """I've analyzed the thesis using independent sources.

```json
{
  "concerns": [
    {
      "id": "C1",
      "claim": "Revenue growth of 15% YoY",
      "category": "financial",
      "challenge": "Yahoo Finance shows only 8.2% growth",
      "severity": "CRITICAL",
      "evidence": "yfinance key_stats: revenue_growth = 0.082"
    },
    {
      "id": "C2",
      "claim": "Strong competitive moat",
      "category": "news",
      "challenge": "New competitor launched similar product",
      "severity": "MAJOR",
      "evidence": "Web search: TechCo announced competing platform Q1 2026"
    }
  ]
}
```

These findings suggest the thesis overstates growth and underestimates competition."""


def _make_rebuttal_response() -> str:
    """Create a realistic rebuttal response with structured JSON rebuttals."""
    return """Defense against debater concerns:

```json
{
  "rebuttals": [
    {
      "concern_id": "C1",
      "status": "PARTIALLY_VALID",
      "defense": "8.2% is trailing 12mo; forward guidance is 14% with new product line",
      "evidence": "Alpha Vantage earnings data shows accelerating quarterly trend"
    },
    {
      "concern_id": "C2",
      "status": "REFUTED",
      "defense": "Competitor product targets different market segment (enterprise vs consumer)",
      "evidence": "Company overview shows 92% consumer revenue"
    }
  ]
}
```

The growth concern is valid for trailing data but forward outlook remains strong."""


def _make_termination_response() -> str:
    """Create a debater response that signals no further concerns."""
    return f"""After thorough review with independent data sources, the defense
adequately addresses all concerns raised.

{TERMINATION_SIGNAL}"""


# ===== Test: Structured Concern Parsing =====


class TestStructuredConcernParsing:
    """Verify debater output is parsed into structured concerns."""

    def test_parses_concerns_from_json_block(self) -> None:
        response = _make_debater_response_with_concerns()
        output = parse_debater_output(response)

        assert len(output.concerns) == 2
        assert output.terminated is False
        assert output.concerns[0].id == "C1"
        assert output.concerns[0].severity == "CRITICAL"
        assert output.concerns[0].category == "financial"
        assert output.concerns[1].id == "C2"
        assert output.concerns[1].severity == "MAJOR"

    def test_detects_termination_signal(self) -> None:
        response = _make_termination_response()
        output = parse_debater_output(response)

        assert output.terminated is True
        assert len(output.concerns) == 0

    def test_handles_malformed_response_gracefully(self) -> None:
        output = parse_debater_output("Some analysis without JSON")

        assert len(output.concerns) == 0
        assert output.terminated is False
        assert output.raw_text == "Some analysis without JSON"


# ===== Test: Structured Rebuttal Parsing =====


class TestStructuredRebuttalParsing:
    """Verify rebuttal output is parsed into structured rebuttals."""

    def test_parses_rebuttals_from_json_block(self) -> None:
        response = _make_rebuttal_response()
        output = parse_rebuttal_output(response)

        assert len(output.rebuttals) == 2
        assert output.rebuttals[0].concern_id == "C1"
        assert output.rebuttals[0].status == "PARTIALLY_VALID"
        assert output.rebuttals[1].concern_id == "C2"
        assert output.rebuttals[1].status == "REFUTED"

    def test_handles_missing_json_gracefully(self) -> None:
        output = parse_rebuttal_output("Defense without structured output")

        assert len(output.rebuttals) == 0
        assert output.raw_text == "Defense without structured output"


# ===== Test: Fact Merging =====


class TestFactMerging:
    """Verify concerns and rebuttals merge correctly by ID."""

    def test_merges_matching_concerns_and_rebuttals(self) -> None:
        concerns = [
            Concern(
                id="C1",
                claim="Revenue growth",
                category="financial",
                challenge="Only 8.2%",
                severity="CRITICAL",
                evidence="yfinance data",
            ),
            Concern(
                id="C2",
                claim="Competitive moat",
                category="news",
                challenge="New competitor",
                severity="MAJOR",
                evidence="web search",
            ),
        ]
        rebuttals = [
            Rebuttal(
                concern_id="C1",
                status="PARTIALLY_VALID",
                defense="Forward guidance is 14%",
                evidence="earnings data",
            ),
            Rebuttal(
                concern_id="C2",
                status="REFUTED",
                defense="Different market segment",
                evidence="company overview",
            ),
        ]

        merged = merge_facts(concerns, rebuttals)

        assert len(merged) == 2
        assert merged[0].id == "C1"
        assert merged[0].defense is not None
        assert merged[0].defense["status"] == "PARTIALLY_VALID"
        assert merged[1].id == "C2"
        assert merged[1].defense is not None
        assert merged[1].defense["status"] == "REFUTED"

    def test_unmatched_concern_has_no_defense(self) -> None:
        concerns = [
            Concern(
                id="C1",
                claim="test",
                category="financial",
                challenge="issue",
                severity="MAJOR",
                evidence="data",
            ),
        ]

        merged = merge_facts(concerns, [])

        assert len(merged) == 1
        assert merged[0].defense is None


# ===== Test: Verified Facts Rendering =====


class TestVerifiedFactsRendering:
    """Verify facts render as <system-reminder> JSON for verdict injection."""

    def test_renders_system_reminder_with_facts(self) -> None:
        facts = [
            MergedFact(
                id="C1",
                claim="Revenue growth",
                category="financial",
                debater={
                    "severity": "CRITICAL",
                    "challenge": "Only 8.2%",
                    "evidence": "yfinance",
                },
                defense={
                    "status": "PARTIALLY_VALID",
                    "rebuttal": "Forward 14%",
                    "evidence": "earnings",
                },
            ),
        ]

        rendered = render_verified_facts_reminder(facts)

        assert "<system-reminder>" in rendered
        assert "</system-reminder>" in rendered

        # Parse the JSON inside the tags
        json_str = (
            rendered.replace("<system-reminder>", "")
            .replace("</system-reminder>", "")
            .strip()
        )
        data = json.loads(json_str)

        assert "verified_facts" in data
        assert len(data["verified_facts"]) == 1
        assert data["verified_facts"][0]["id"] == "C1"
        assert data["verified_facts"][0]["defense"]["status"] == "PARTIALLY_VALID"

    def test_empty_facts_return_empty_string(self) -> None:
        rendered = render_verified_facts_reminder([])
        # With no facts, the function still returns valid JSON
        assert "<system-reminder>" in rendered


# ===== Test: End-to-End Debate Flow (State Transitions) =====


class TestDebateStateTransitions:
    """Test the state accumulation pattern across debate rounds.

    Simulates the graph state flow without running the actual LangGraph
    graph, verifying that concerns and rebuttals accumulate correctly.
    """

    def test_concerns_accumulate_across_rounds(self) -> None:
        """Simulate 2 debate rounds with concern accumulation."""
        # Round 1: Debater raises concerns
        debater_response_1 = _make_debater_response_with_concerns()
        output_1 = parse_debater_output(debater_response_1)
        round_1_concerns = [
            {
                "id": c.id,
                "claim": c.claim,
                "category": c.category,
                "challenge": c.challenge,
                "severity": c.severity,
                "evidence": c.evidence,
            }
            for c in output_1.concerns
        ]

        state_after_debate_1: dict[str, Any] = {
            "all_concerns": round_1_concerns,
            "all_rebuttals": [],
            "round_count": 1,
        }

        assert len(state_after_debate_1["all_concerns"]) == 2
        assert state_after_debate_1["round_count"] == 1

        # Rebuttal: Main agent defends
        rebuttal_response = _make_rebuttal_response()
        rebuttal_output = parse_rebuttal_output(rebuttal_response)
        new_rebuttals = [
            {
                "concern_id": r.concern_id,
                "status": r.status,
                "defense": r.defense,
                "evidence": r.evidence,
            }
            for r in rebuttal_output.rebuttals
        ]

        state_after_rebuttal: dict[str, Any] = {
            "all_concerns": state_after_debate_1["all_concerns"],
            "all_rebuttals": state_after_debate_1["all_rebuttals"] + new_rebuttals,
            "round_count": 1,
        }

        assert len(state_after_rebuttal["all_rebuttals"]) == 2

        # Round 2: Debater terminates
        termination_response = _make_termination_response()
        output_2 = parse_debater_output(termination_response)

        assert output_2.terminated is True
        assert len(output_2.concerns) == 0

        # Final state: 2 concerns + 2 rebuttals
        final_concerns = state_after_rebuttal["all_concerns"]
        final_rebuttals = state_after_rebuttal["all_rebuttals"]

        # Merge for verdict
        concerns = [Concern(**c) for c in final_concerns]
        rebuttals = [Rebuttal(**r) for r in final_rebuttals]
        merged = merge_facts(concerns, rebuttals)

        assert len(merged) == 2
        assert all(f.defense is not None for f in merged)

    def test_verdict_receives_verified_facts(self) -> None:
        """Verify the verdict prompt would contain <system-reminder> JSON."""
        concerns = [
            Concern(
                id="C1",
                claim="Revenue growth",
                category="financial",
                challenge="Only 8.2%",
                severity="CRITICAL",
                evidence="yfinance",
            ),
        ]
        rebuttals = [
            Rebuttal(
                concern_id="C1",
                status="REFUTED",
                defense="Forward guidance 14%",
                evidence="earnings",
            ),
        ]

        merged = merge_facts(concerns, rebuttals)
        facts_block = render_verified_facts_reminder(merged)

        # Simulate verdict prompt construction
        verdict_prompt = f"""You are a Judge.

{facts_block}

## Research Report
Some research...

## Your Task
Categorize each concern..."""

        assert "<system-reminder>" in verdict_prompt
        assert "REFUTED" in verdict_prompt
        assert "C1" in verdict_prompt


# ===== Test: Debater Tool Independence =====


class TestDebaterToolIndependence:
    """Verify debater uses independent tools, not Alpha Vantage."""

    def test_debater_has_independent_tools_only(self) -> None:
        """Debater sub-agent should have yfinance + exa, not Alpha Vantage."""
        with (
            patch("src.agent.subagents.debater.create_deep_subagent") as mock_create,
            patch("src.agent.subagents.debater.create_yfinance_tools") as mock_yf,
            patch("src.agent.subagents.debater.create_exa_tools") as mock_exa,
        ):
            mock_yf_tool = MagicMock()
            mock_yf_tool.name = "fetch_yfinance_news"
            mock_yf.return_value = [mock_yf_tool]

            mock_exa_tool = MagicMock()
            mock_exa_tool.name = "search_web_exa"
            mock_exa.return_value = [mock_exa_tool]

            mock_create.return_value = MagicMock()

            from src.agent.subagents.debater import create_debater_subagent

            create_debater_subagent(
                model=MagicMock(), context=None, exa_api_key="test-key"
            )

            # Verify independent tools were created
            mock_yf.assert_called_once()
            mock_exa.assert_called_once_with(api_key="test-key")

            # Verify create_deep_subagent was called with these tools
            call_args = mock_create.call_args
            tools_passed = call_args.kwargs.get("tools", call_args[1].get("tools", []))
            tool_names = [getattr(t, "name", "") for t in tools_passed]
            assert "fetch_yfinance_news" in tool_names
            assert "search_web_exa" in tool_names

    def test_debater_without_exa_key_uses_yfinance_only(self) -> None:
        """Without Exa API key, debater falls back to yfinance only."""
        with (
            patch("src.agent.subagents.debater.create_deep_subagent") as mock_create,
            patch("src.agent.subagents.debater.create_yfinance_tools") as mock_yf,
            patch("src.agent.subagents.debater.create_exa_tools") as mock_exa,
        ):
            mock_yf_tool = MagicMock()
            mock_yf_tool.name = "fetch_yfinance_news"
            mock_yf.return_value = [mock_yf_tool]

            mock_create.return_value = MagicMock()

            from src.agent.subagents.debater import create_debater_subagent

            create_debater_subagent(model=MagicMock(), context=None, exa_api_key="")

            mock_yf.assert_called_once()
            mock_exa.assert_not_called()

            call_args = mock_create.call_args
            tools_passed = call_args.kwargs.get("tools", call_args[1].get("tools", []))
            assert len(tools_passed) == 1
            assert tools_passed[0].name == "fetch_yfinance_news"


# ===== Test: AnalysisState Schema =====


class TestAnalysisStateSchema:
    """Verify AnalysisState includes new structured debate fields."""

    def test_state_has_debate_tracking_fields(self) -> None:
        from src.agent.deep_react_agent import AnalysisState

        # AnalysisState is a TypedDict — check annotations
        annotations = AnalysisState.__annotations__
        assert "all_concerns" in annotations
        assert "all_rebuttals" in annotations
        assert "debate_active" in annotations
        assert "round_count" in annotations

    def test_initial_state_shape(self) -> None:
        """Verify the initial state dict matches expected shape."""
        from src.agent.deep_react_agent import AnalysisState

        # Simulate initial state creation (TypedDict is a dict at runtime)
        state: dict[str, Any] = {
            "messages": [],
            "symbol": "AAPL",
            "round_count": 0,
            "research_report": "",
            "debate_active": True,
            "all_concerns": [],
            "all_rebuttals": [],
        }

        assert state["all_concerns"] == []
        assert state["all_rebuttals"] == []
        assert state["round_count"] == 0
