"""
Structured types for debate exchange and fact verification.

Provides parsing, merging, and rendering of debater concerns
and rebuttal defenses into verified facts for verdict injection.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()


@dataclass
class Concern:
    id: str
    claim: str
    category: str
    challenge: str
    severity: str
    evidence: str


@dataclass
class DebaterOutput:
    concerns: list[Concern] = field(default_factory=list)
    terminated: bool = False
    raw_text: str = ""


@dataclass
class Rebuttal:
    concern_id: str
    status: str  # REFUTED | PARTIALLY_VALID | CONCEDED
    defense: str
    evidence: str


@dataclass
class RebuttalOutput:
    rebuttals: list[Rebuttal] = field(default_factory=list)
    raw_text: str = ""


@dataclass
class MergedFact:
    id: str
    claim: str
    category: str
    debater: dict
    defense: dict | None = None


def _extract_json_block(text: str) -> dict | None:
    """Extract first JSON code block from text."""
    pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Fallback: try outermost { ... } in the text (O(1) parse attempts)
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(text[first_brace : last_brace + 1])
        except json.JSONDecodeError:
            pass
    return None


def parse_debater_output(response: str) -> DebaterOutput:
    """Parse debater's response into structured concerns."""
    from .subagents.debater import TERMINATION_SIGNAL

    # Strict match: signal must appear on its own line (not embedded in analysis)
    # to avoid false termination when LLM quotes the signal alongside concerns
    response_lines = [line.strip() for line in response.strip().splitlines()]
    if TERMINATION_SIGNAL in response_lines:
        return DebaterOutput(terminated=True, raw_text=response)

    data = _extract_json_block(response)
    if not data or "concerns" not in data:
        logger.warning("Could not parse structured debater output, using raw text")
        return DebaterOutput(raw_text=response)

    concerns = [
        Concern(
            id=c.get("id", f"C{i+1}"),
            claim=c.get("claim", ""),
            category=c.get("category", "unknown"),
            challenge=c.get("challenge", ""),
            severity=c.get("severity", "MAJOR"),
            evidence=c.get("evidence", ""),
        )
        for i, c in enumerate(data["concerns"])
    ]
    return DebaterOutput(concerns=concerns, raw_text=response)


def parse_rebuttal_output(response: str) -> RebuttalOutput:
    """Parse main agent's rebuttal into structured defenses."""
    data = _extract_json_block(response)
    if not data or "rebuttals" not in data:
        logger.warning("Could not parse structured rebuttal output, using raw text")
        return RebuttalOutput(raw_text=response)

    rebuttals = [
        Rebuttal(
            concern_id=r.get("concern_id", ""),
            status=r.get("status", "PARTIALLY_VALID"),
            defense=r.get("defense", ""),
            evidence=r.get("evidence", ""),
        )
        for r in data["rebuttals"]
    ]
    return RebuttalOutput(rebuttals=rebuttals, raw_text=response)


def merge_facts(concerns: list[Concern], rebuttals: list[Rebuttal]) -> list[MergedFact]:
    """Merge debater concerns with rebuttal defenses by ID."""
    rebuttal_map = {r.concern_id: r for r in rebuttals}

    return [
        MergedFact(
            id=c.id,
            claim=c.claim,
            category=c.category,
            debater={
                "severity": c.severity,
                "challenge": c.challenge,
                "evidence": c.evidence,
            },
            defense=(
                {
                    "status": rebuttal_map[c.id].status,
                    "rebuttal": rebuttal_map[c.id].defense,
                    "evidence": rebuttal_map[c.id].evidence,
                }
                if c.id in rebuttal_map
                else None
            ),
        )
        for c in concerns
    ]


def render_verified_facts_reminder(facts: list[MergedFact]) -> str:
    """Render merged facts as a <system-reminder> JSON block for verdict injection."""
    payload = {
        "verified_facts": [
            {
                "id": f.id,
                "claim": f.claim,
                "category": f.category,
                "debater": f.debater,
                "defense": f.defense,
            }
            for f in facts
        ]
    }
    return f"<system-reminder>\n{json.dumps(payload, indent=2)}\n</system-reminder>"
