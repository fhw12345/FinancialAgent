"""Tests for structured debate types and JSON parsing."""

import json

from src.agent.debate_types import (
    Concern,
    MergedFact,
    Rebuttal,
    merge_facts,
    parse_debater_output,
    parse_rebuttal_output,
    render_verified_facts_reminder,
)


class TestParseDebaterOutput:
    def test_extracts_json_from_response(self) -> None:
        response = """I found several issues.

```json
{
  "concerns": [
    {"id": "C1", "claim": "EPS growth", "category": "financial", "challenge": "-62%", "severity": "CRITICAL", "evidence": "yfinance data"}
  ]
}
```

These are serious problems."""
        output = parse_debater_output(response)
        assert len(output.concerns) == 1
        assert output.concerns[0].id == "C1"
        assert output.concerns[0].severity == "CRITICAL"

    def test_returns_empty_on_termination_signal(self) -> None:
        output = parse_debater_output("NO FURTHER CONCERNS")
        assert len(output.concerns) == 0
        assert output.terminated is True

    def test_handles_malformed_json(self) -> None:
        output = parse_debater_output("Some text without JSON")
        assert len(output.concerns) == 0
        assert output.terminated is False
        assert output.raw_text == "Some text without JSON"


class TestParseRebuttalOutput:
    def test_extracts_rebuttals(self) -> None:
        response = """Defense:

```json
{
  "rebuttals": [
    {"concern_id": "C1", "status": "REFUTED", "defense": "Correct FY growth is +22.9%", "evidence": "sub-agent data"}
  ]
}
```"""
        output = parse_rebuttal_output(response)
        assert len(output.rebuttals) == 1
        assert output.rebuttals[0].status == "REFUTED"


class TestMergeFacts:
    def test_merges_concerns_and_rebuttals(self) -> None:
        concerns = [
            Concern(
                id="C1",
                claim="test",
                category="financial",
                challenge="bad",
                severity="MAJOR",
                evidence="data",
            )
        ]
        rebuttals = [
            Rebuttal(
                concern_id="C1",
                status="REFUTED",
                defense="actually good",
                evidence="proof",
            )
        ]
        facts = merge_facts(concerns, rebuttals)
        assert len(facts) == 1
        assert facts[0].id == "C1"
        assert facts[0].defense is not None
        assert facts[0].defense["status"] == "REFUTED"

    def test_unmatched_concern_has_no_defense(self) -> None:
        concerns = [
            Concern(
                id="C1",
                claim="test",
                category="financial",
                challenge="bad",
                severity="MAJOR",
                evidence="data",
            )
        ]
        facts = merge_facts(concerns, [])
        assert len(facts) == 1
        assert facts[0].defense is None


class TestRenderReminder:
    def test_renders_system_reminder_json(self) -> None:
        facts = [
            MergedFact(
                id="C1",
                claim="test",
                category="financial",
                debater={"severity": "MAJOR", "challenge": "bad", "evidence": "data"},
                defense={"status": "REFUTED", "rebuttal": "good", "evidence": "proof"},
            )
        ]
        rendered = render_verified_facts_reminder(facts)
        assert "<system-reminder>" in rendered
        assert "</system-reminder>" in rendered
        data = json.loads(
            rendered.replace("<system-reminder>", "")
            .replace("</system-reminder>", "")
            .strip()
        )
        assert len(data["verified_facts"]) == 1
