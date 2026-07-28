"""Strict structured types for Deep debate and verdict output."""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

ConcernCategory = Literal["technical", "fundamental", "valuation", "risk"]
ConcernSeverity = Literal["MAJOR", "MINOR"]
RebuttalStatus = Literal["REFUTED", "PARTIALLY_VALID", "CONCEDED"]
VerdictAction = Literal["BUY", "HOLD", "SELL"]
VerdictConviction = Literal["HIGH", "MEDIUM", "LOW"]
VerdictRiskLevel = Literal["HIGH", "MODERATE", "LOW"]
ConcernAssessmentStatus = Literal[
    "VERIFIED",
    "NEEDS_MORE_EVIDENCE",
    "CONTRADICTED",
]


class StrictModel(BaseModel):
    """Base model for LLM contracts that reject unknown fields and coercion."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )


class Concern(StrictModel):
    id: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    category: ConcernCategory
    challenge: str = Field(min_length=1)
    severity: ConcernSeverity
    evidence: str = Field(min_length=1)


class _DebaterPayload(StrictModel):
    concerns: list[Concern] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> _DebaterPayload:
        ids = [concern.id for concern in self.concerns]
        if len(ids) != len(set(ids)):
            raise ValueError("concern ids must be unique")
        return self


class DebaterOutput(StrictModel):
    concerns: list[Concern]
    terminated: bool
    raw_text: str


class Rebuttal(StrictModel):
    concern_id: str = Field(min_length=1)
    status: RebuttalStatus
    defense: str = Field(min_length=1)
    evidence: str = Field(min_length=1)


class _RebuttalPayload(StrictModel):
    rebuttals: list[Rebuttal] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> _RebuttalPayload:
        ids = [rebuttal.concern_id for rebuttal in self.rebuttals]
        if len(ids) != len(set(ids)):
            raise ValueError("rebuttal concern_ids must be unique")
        return self


class RebuttalOutput(StrictModel):
    rebuttals: list[Rebuttal]
    raw_text: str


class MergedFact(StrictModel):
    id: str
    claim: str
    category: ConcernCategory
    debater: dict[str, str]
    defense: dict[str, str] | None = None


class ConcernAssessment(StrictModel):
    concern_id: str = Field(min_length=1)
    assessment: ConcernAssessmentStatus
    reasoning: str = Field(min_length=1)
    evidence: str = Field(min_length=1)


class DeepVerdict(StrictModel):
    """Structured verdict whose Markdown report remains the user-facing answer."""

    report_markdown: str = Field(
        min_length=1,
        description=(
            "Self-contained final investment committee report in Markdown with "
            "an explicit Action or Recommendation field."
        ),
    )
    action: VerdictAction
    conviction: VerdictConviction
    risk_level: VerdictRiskLevel
    key_insight: str = Field(min_length=1)
    concern_assessments: list[ConcernAssessment]

    @model_validator(mode="after")
    def validate_report_action(self) -> DeepVerdict:
        normalized = self.report_markdown.replace("**", "")
        actions: set[str] = set()
        found_field = False
        field_pattern = re.compile(r"(?i)\b(?:Action|Recommendation)\b\s*([:|])")
        for line in normalized.splitlines():
            matches = list(field_pattern.finditer(line))
            for index, match in enumerate(matches):
                found_field = True
                value_end = (
                    matches[index + 1].start()
                    if index + 1 < len(matches)
                    else len(line)
                )
                value = line[match.end() : value_end]
                if match.group(1) == "|":
                    value = value.split("|", maxsplit=1)[0]
                value = value.strip(" \t:|;,.")
                action_match = re.fullmatch(
                    r"(?i)(BUY|HOLD|SELL)",
                    value,
                )
                if action_match is None:
                    raise ValueError(
                        "each report Action or Recommendation field must contain "
                        "exactly one BUY, HOLD, or SELL value"
                    )
                actions.add(action_match.group(1).upper())
        if not found_field:
            raise ValueError(
                "report_markdown must include an explicit Action or "
                "Recommendation field"
            )
        if actions != {self.action}:
            raise ValueError("report_markdown action must match structured action")
        return self


class DebateOutputValidationError(ValueError):
    """Base error raised when a Deep debate response violates its JSON contract."""

    def __init__(self, output_type: str, raw_text: str, cause: Exception) -> None:
        super().__init__(
            f"Invalid {output_type} output: expected one strict JSON object"
        )
        self.output_type = output_type
        self.raw_text = raw_text
        self.__cause__ = cause


class DebaterOutputValidationError(DebateOutputValidationError):
    """Raised for invalid debater JSON."""


class RebuttalOutputValidationError(DebateOutputValidationError):
    """Raised for invalid rebuttal JSON."""


class RebuttalCoverageValidationError(ValueError):
    """Raised when rebuttals do not cover the exact debated concern IDs."""

    def __init__(self, expected_ids: list[str], actual_ids: list[str]) -> None:
        super().__init__(
            "Invalid rebuttal coverage: expected exactly "
            f"{expected_ids}, received {actual_ids}"
        )
        self.expected_ids = expected_ids
        self.actual_ids = actual_ids


class VerdictAssessmentValidationError(ValueError):
    """Raised when verdict assessments do not match the debated concerns."""

    def __init__(self, expected_ids: list[str], actual_ids: list[str]) -> None:
        super().__init__(
            "Invalid verdict concern assessments: expected exactly "
            f"{expected_ids}, received {actual_ids}"
        )
        self.expected_ids = expected_ids
        self.actual_ids = actual_ids


def parse_debater_output(response: str) -> DebaterOutput:
    """Validate a pure-JSON concern object or the standalone termination signal."""
    from .subagents.debater import TERMINATION_SIGNAL

    response_lines = [line.strip() for line in response.strip().splitlines()]
    if TERMINATION_SIGNAL in response_lines:
        return DebaterOutput(concerns=[], terminated=True, raw_text=response)

    try:
        payload = _DebaterPayload.model_validate_json(response, strict=True)
    except ValidationError as exc:
        raise DebaterOutputValidationError("debater", response, exc) from exc
    return DebaterOutput(
        concerns=payload.concerns,
        terminated=False,
        raw_text=response,
    )


def parse_rebuttal_output(response: str) -> RebuttalOutput:
    """Validate a pure-JSON rebuttal object."""
    try:
        payload = _RebuttalPayload.model_validate_json(response, strict=True)
    except ValidationError as exc:
        raise RebuttalOutputValidationError("rebuttal", response, exc) from exc
    return RebuttalOutput(rebuttals=payload.rebuttals, raw_text=response)


def namespace_concern_ids(
    concerns: list[Concern],
    round_number: int,
) -> list[Concern]:
    """Make model-generated concern IDs unique across debate rounds."""
    return [
        concern.model_copy(update={"id": f"R{round_number}-{concern.id}"})
        for concern in concerns
    ]


def validate_verdict_assessments(
    verdict: DeepVerdict,
    concerns: list[Concern],
) -> None:
    """Require one verdict assessment for every debated concern."""
    expected_ids = [concern.id for concern in concerns]
    actual_ids = [assessment.concern_id for assessment in verdict.concern_assessments]
    if Counter(expected_ids) != Counter(actual_ids):
        raise VerdictAssessmentValidationError(expected_ids, actual_ids)


def validate_rebuttal_coverage(
    rebuttals: list[Rebuttal],
    concerns: list[Concern],
) -> None:
    """Require one rebuttal for every concern ID shown to the defender."""
    expected_ids = [concern.id for concern in concerns]
    actual_ids = [rebuttal.concern_id for rebuttal in rebuttals]
    if Counter(expected_ids) != Counter(actual_ids):
        raise RebuttalCoverageValidationError(expected_ids, actual_ids)


def merge_facts(concerns: list[Concern], rebuttals: list[Rebuttal]) -> list[MergedFact]:
    """Merge debater concerns with rebuttal defenses by concern ID."""
    rebuttal_map = {rebuttal.concern_id: rebuttal for rebuttal in rebuttals}
    return [
        MergedFact(
            id=concern.id,
            claim=concern.claim,
            category=concern.category,
            debater={
                "severity": concern.severity,
                "challenge": concern.challenge,
                "evidence": concern.evidence,
            },
            defense=(
                {
                    "status": rebuttal_map[concern.id].status,
                    "rebuttal": rebuttal_map[concern.id].defense,
                    "evidence": rebuttal_map[concern.id].evidence,
                }
                if concern.id in rebuttal_map
                else None
            ),
        )
        for concern in concerns
    ]


def render_verified_facts_reminder(facts: list[MergedFact]) -> str:
    """Render merged facts as a system-reminder JSON block for the verdict."""
    payload = {"verified_facts": [fact.model_dump() for fact in facts]}
    return f"<system-reminder>\n{json.dumps(payload, indent=2)}\n</system-reminder>"
