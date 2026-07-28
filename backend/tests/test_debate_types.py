"""Tests for strict Deep debate and verdict schemas."""

import json

import pytest
from pydantic import ValidationError

from src.agent.debate_types import (
    Concern,
    DebaterOutputValidationError,
    DeepVerdict,
    MergedFact,
    Rebuttal,
    RebuttalCoverageValidationError,
    RebuttalOutputValidationError,
    VerdictAssessmentValidationError,
    merge_facts,
    namespace_concern_ids,
    parse_debater_output,
    parse_rebuttal_output,
    render_verified_facts_reminder,
    validate_rebuttal_coverage,
    validate_verdict_assessments,
)


def concern_json() -> str:
    return json.dumps(
        {
            "concerns": [
                {
                    "id": "C1",
                    "claim": "EPS growth",
                    "category": "fundamental",
                    "challenge": "Growth slowed",
                    "severity": "MAJOR",
                    "evidence": "FY filing",
                }
            ]
        }
    )


def rebuttal_json() -> str:
    return json.dumps(
        {
            "rebuttals": [
                {
                    "concern_id": "C1",
                    "status": "REFUTED",
                    "defense": "Forward growth is 22.9%",
                    "evidence": "Management guidance",
                }
            ]
        }
    )


class TestParseDebaterOutput:
    def test_accepts_one_pure_json_object(self) -> None:
        output = parse_debater_output(concern_json())
        assert output.concerns[0].id == "C1"
        assert output.concerns[0].severity == "MAJOR"
        assert output.terminated is False

    @pytest.mark.parametrize(
        "response",
        [
            "Some text without JSON",
            f"```json\n{concern_json()}\n```",
            f"Analysis first.\n{concern_json()}",
            '{"concerns": []}',
            '{"concerns": [{"id": "C1"}]}',
            '{"concerns": [], "unexpected": true}',
        ],
    )
    def test_rejects_invalid_or_wrapped_output(self, response: str) -> None:
        with pytest.raises(DebaterOutputValidationError):
            parse_debater_output(response)

    def test_preserves_standalone_termination_behavior(self) -> None:
        output = parse_debater_output("Review complete.\n\n   NO FURTHER CONCERNS   \n")
        assert output.concerns == []
        assert output.terminated is True

    def test_embedded_termination_signal_does_not_terminate(self) -> None:
        response = concern_json().replace(
            '"EPS growth"',
            '"The phrase NO FURTHER CONCERNS was quoted"',
        )
        output = parse_debater_output(response)
        assert output.terminated is False
        assert len(output.concerns) == 1

    def test_rejects_duplicate_concern_ids(self) -> None:
        response = json.dumps(
            {
                "concerns": [
                    json.loads(concern_json())["concerns"][0],
                    json.loads(concern_json())["concerns"][0],
                ]
            }
        )
        with pytest.raises(DebaterOutputValidationError):
            parse_debater_output(response)


class TestParseRebuttalOutput:
    def test_accepts_one_pure_json_object(self) -> None:
        output = parse_rebuttal_output(rebuttal_json())
        assert output.rebuttals[0].status == "REFUTED"

    @pytest.mark.parametrize(
        "response",
        [
            "Defense without JSON",
            f"```json\n{rebuttal_json()}\n```",
            '{"rebuttals": []}',
            '{"rebuttals": [{"concern_id": "C1", "status": "UNKNOWN"}]}',
        ],
    )
    def test_rejects_invalid_or_wrapped_output(self, response: str) -> None:
        with pytest.raises(RebuttalOutputValidationError):
            parse_rebuttal_output(response)

    def test_rejects_duplicate_rebuttal_ids(self) -> None:
        response = json.dumps(
            {
                "rebuttals": [
                    json.loads(rebuttal_json())["rebuttals"][0],
                    json.loads(rebuttal_json())["rebuttals"][0],
                ]
            }
        )
        with pytest.raises(RebuttalOutputValidationError):
            parse_rebuttal_output(response)


class TestMergeFacts:
    def test_merges_concerns_and_rebuttals(self) -> None:
        concerns = [
            Concern(
                id="C1",
                claim="test",
                category="fundamental",
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
        assert facts[0].defense is not None
        assert facts[0].defense["status"] == "REFUTED"

    def test_unmatched_concern_has_no_defense(self) -> None:
        concern = Concern(
            id="C1",
            claim="test",
            category="risk",
            challenge="bad",
            severity="MINOR",
            evidence="data",
        )
        assert merge_facts([concern], [])[0].defense is None


def test_renders_system_reminder_json() -> None:
    fact = MergedFact(
        id="C1",
        claim="test",
        category="fundamental",
        debater={"severity": "MAJOR", "challenge": "bad", "evidence": "data"},
        defense={"status": "REFUTED", "rebuttal": "good", "evidence": "proof"},
    )
    rendered = render_verified_facts_reminder([fact])
    data = json.loads(
        rendered.replace("<system-reminder>", "")
        .replace("</system-reminder>", "")
        .strip()
    )
    assert data["verified_facts"][0]["id"] == "C1"


def test_namespaces_concern_ids_by_round() -> None:
    concern = Concern(
        id="C1",
        claim="test",
        category="risk",
        challenge="bad",
        severity="MINOR",
        evidence="data",
    )
    assert namespace_concern_ids([concern], round_number=2)[0].id == "R2-C1"
    assert concern.id == "C1"


def test_verdict_assessments_must_match_all_concerns_exactly() -> None:
    concerns = [
        Concern(
            id="R1-C1",
            claim="test",
            category="risk",
            challenge="bad",
            severity="MINOR",
            evidence="data",
        )
    ]
    verdict = DeepVerdict(
        report_markdown="# Verdict\n\n**Action**: HOLD",
        action="HOLD",
        conviction="LOW",
        risk_level="MODERATE",
        key_insight="More evidence is required.",
        concern_assessments=[],
    )
    with pytest.raises(VerdictAssessmentValidationError):
        validate_verdict_assessments(verdict, concerns)


def test_rebuttals_must_preserve_and_cover_exact_concern_ids() -> None:
    concerns = [
        Concern(
            id="R1-C1",
            claim="test",
            category="risk",
            challenge="bad",
            severity="MINOR",
            evidence="data",
        )
    ]
    rebuttals = [
        Rebuttal(
            concern_id="C1",
            status="REFUTED",
            defense="good",
            evidence="proof",
        )
    ]
    with pytest.raises(RebuttalCoverageValidationError):
        validate_rebuttal_coverage(rebuttals, concerns)


def test_structured_verdict_rejects_invalid_machine_fields() -> None:
    with pytest.raises(ValidationError):
        DeepVerdict.model_validate(
            {
                "report_markdown": "# Verdict",
                "action": "MAYBE",
                "conviction": "HIGH",
                "risk_level": "LOW",
                "key_insight": "Durable growth.",
                "concern_assessments": [],
            },
            strict=True,
        )


@pytest.mark.parametrize(
    "report_markdown",
    [
        "# Verdict\n\n**Action:** BUY",
        "# Verdict\n\nRecommendation: BUY",
        "# Verdict\n\n| Action | BUY |",
    ],
)
def test_structured_verdict_accepts_explicit_markdown_action_forms(
    report_markdown: str,
) -> None:
    verdict = DeepVerdict(
        report_markdown=report_markdown,
        action="BUY",
        conviction="HIGH",
        risk_level="LOW",
        key_insight="Durable growth.",
        concern_assessments=[],
    )
    assert verdict.action == "BUY"


@pytest.mark.parametrize(
    "report_markdown",
    [
        "Action: BUY\n\nRecommendation: SELL",
        "Action: BUY; Recommendation: SELL",
        "Action: BUY / SELL",
    ],
)
def test_structured_verdict_rejects_conflicting_explicit_actions(
    report_markdown: str,
) -> None:
    with pytest.raises(ValidationError):
        DeepVerdict(
            report_markdown=report_markdown,
            action="BUY",
            conviction="LOW",
            risk_level="HIGH",
            key_insight="The report is internally inconsistent.",
            concern_assessments=[],
        )


def test_structured_verdict_rejects_negated_action_value() -> None:
    with pytest.raises(ValidationError, match="must contain exactly one"):
        DeepVerdict(
            report_markdown="Action: DO NOT BUY",
            action="BUY",
            conviction="LOW",
            risk_level="HIGH",
            key_insight="The field cannot negate the machine action.",
            concern_assessments=[],
        )
