"""Validate typed assertions, never certify free prose or execute model-generated formula code."""

import json
import re
from typing import cast

from ...models.evidence import (
    ClaimResult,
    EvidenceRecord,
    EvidenceSnapshot,
    ResearchClaim,
    ResearchDossier,
)
from ..portfolio_risk.calendar import completed_session, sessions
from .identity import digest, same_value

CLAIM_INSTRUCTION = """
Evidence contract: use only ev_ IDs returned by the sealed tools. End your report with
<claims-json>{"claims":[{"kind":"fact","symbol":"SYMBOL","metric":"price.close_reference",
"value":100.0,"unit":"USD","period":"session","period_end":"YYYY-MM-DD","evidence_ids":["ev_ID"]}]}</claims-json>.
Copy exact metric/unit/period/end and IDs from actual tool records; the example is not data.
Include every material numeric assertion as a structured claim. Do not set verification or
materiality yourself. Optional method is free_cash_flow@1 or net_margin@1; no formulas/code.
Hypotheses/judgments and free prose remain unverified. If evidence is missing, say so.
"""


def _resolve(
    snapshot: EvidenceSnapshot, identifier: str
) -> tuple[list[EvidenceRecord], str | None]:
    exact = [r for r in snapshot.records if r.evidence_id == identifier]
    if exact:
        return exact, None
    aliases = [
        r for r in snapshot.records if identifier.strip("[]") in r.legacy_aliases
    ]
    if len(aliases) > 1:
        return [], "AMBIGUOUS_LEGACY_ALIAS"
    # New writes require unique server IDs; even a single old alias is not authority.
    return [], "LEGACY_ALIAS_UNRESOLVED" if aliases else "EVIDENCE_NOT_IN_MANIFEST"


def validate_claim(
    snapshot: EvidenceSnapshot, claim: ResearchClaim, index: int = 0
) -> ClaimResult:
    reasons = []
    records = []
    computed = None
    if snapshot.state != "sealed":
        reasons.append("SNAPSHOT_NOT_SEALED")
    if claim.symbol != snapshot.symbol:
        reasons.append("SYMBOL_MISMATCH")
    if not claim.evidence_ids and claim.kind in ("fact", "derived"):
        reasons.append("EVIDENCE_REQUIRED")
    for identifier in claim.evidence_ids:
        resolved, error = _resolve(snapshot, identifier)
        records.extend(resolved)
        if error:
            reasons.append(error)
    conflicted = {eid for ids in snapshot.conflicts.values() for eid in ids}
    for record in records:
        if record.symbol != claim.symbol:
            reasons.append("SYMBOL_MISMATCH")
        if record.quality != "available":
            reasons.append("EVIDENCE_" + record.quality.upper())
        if record.evidence_id in conflicted:
            reasons.append("CONFLICTING_EVIDENCE")
        if record.period != claim.period or record.period_end != claim.period_end:
            reasons.append("PERIOD_MISMATCH")
        if record.period == "unknown" or (
            record.period in ("ttm", "annual", "quarter", "session")
            and record.period_end is None
        ):
            reasons.append("PERIOD_UNVERIFIED")
        if record.period_end and record.period_end > snapshot.requested_as_of.date():
            reasons.append("ECONOMIC_PERIOD_AFTER_CUTOFF")
        if (
            snapshot.strategy_contract
            and record.period in ("annual", "quarter", "ttm")
            and record.period_end
        ):
            if (
                snapshot.requested_as_of.date() - record.period_end
            ).days > snapshot.strategy_contract.parameters.max_financial_age_days:
                reasons.append("STALE_FINANCIAL_PERIOD")
        if record.metric.startswith("price."):
            lag = (
                snapshot.strategy_contract.parameters.max_price_lag_sessions
                if snapshot.strategy_contract
                else 0
            )
            if record.period == "session" and record.period_end not in sessions(
                completed_session(snapshot.requested_as_of), lag + 1
            ):
                reasons.append("STALE_SESSION")
            if record.period == "instant":
                reasons.append("QUOTE_FRESHNESS_POLICY_UNCONFIRMED")
        if record.observed_at and record.observed_at > snapshot.requested_as_of:
            reasons.append("OBSERVATION_AFTER_CUTOFF")
        if record.published_at and record.published_at > snapshot.requested_as_of:
            reasons.append("PUBLICATION_AFTER_CUTOFF")
        if snapshot.mode == "strict_historical" and (
            record.point_in_time_status != "verified" or record.published_at is None
        ):
            reasons.append("HISTORICAL_PIT_UNPROVEN")
    if claim.kind == "fact":
        if not records or any(r.metric != claim.metric for r in records):
            reasons.append("METRIC_MISMATCH")
        if any(r.unit != claim.unit for r in records):
            reasons.append("UNIT_MISMATCH")
        if any(not same_value(r.value, claim.value) for r in records):
            reasons.append("VALUE_MISMATCH")
        if claim.method is not None:
            reasons.append("FACT_METHOD_NOT_ALLOWED")
    elif claim.kind == "derived":
        required = {
            "free_cash_flow@1": (
                "operating_cash_flow",
                "capital_expenditure",
                "free_cash_flow",
            ),
            "net_margin@1": ("net_income", "revenue", "net_margin"),
        }.get(claim.method or "")
        if (
            required is None
            or len(records) != 2
            or {r.metric for r in records} != set(required[:2])
            or claim.metric != required[2]
        ):
            reasons.append("CALCULATOR_INPUT_MISMATCH")
        elif (
            not re.fullmatch(r"[A-Z]{3}", records[0].unit)
            or len({r.unit for r in records}) != 1
            or not all(isinstance(r.value, float) for r in records)
        ):
            reasons.append("CALCULATOR_UNIT_MISMATCH")
        else:
            values = {r.metric: cast(float, r.value) for r in records}
            a, b = values[required[0]], values[required[1]]
            if claim.method == "free_cash_flow@1":
                if b < 0:
                    reasons.append("CAPEX_SIGN_UNSUPPORTED")
                computed = a - b
                if claim.unit != records[0].unit:
                    reasons.append("UNIT_MISMATCH")
            else:
                if b == 0:
                    reasons.append("ZERO_DENOMINATOR")
                else:
                    computed = a / b
                if claim.unit != "ratio":
                    reasons.append("UNIT_MISMATCH")
            if not same_value(computed, claim.value):
                reasons.append("VALUE_MISMATCH")
    else:
        # A number embedded in a hypothesis/judgment never gains verified fact status.
        if claim.value is not None:
            reasons.append("NUMERIC_JUDGMENT_UNVERIFIED")
        reasons.append("PROSE_UNVERIFIED")
    return ClaimResult(
        claim_id="claim_"
        + digest([snapshot.snapshot_id, index, claim.model_dump(mode="json")]),
        claim=claim,
        status=(
            "unverified"
            if claim.kind in ("hypothesis", "judgment")
            else "rejected" if reasons else "matches_snapshot"
        ),
        reasons=sorted(set(reasons)),
        evidence_ids=[r.evidence_id for r in records],
        computed_value=computed,
    )


def build_dossier(snapshot: EvidenceSnapshot, report: str) -> ResearchDossier:
    errors = []
    claims = []
    blocks = re.findall(r"<claims-json>(.*?)</claims-json>", report, flags=re.DOTALL)
    try:
        if len(blocks) != 1 or len(blocks[0]) > 64000:
            raise ValueError("Missing/bounded claim block")
        payload = json.loads(blocks[0])
        if (
            set(payload) != {"claims"}
            or not isinstance(payload["claims"], list)
            or not 1 <= len(payload["claims"]) <= 64
        ):
            raise ValueError("Invalid claim count")
        claims = [
            validate_claim(snapshot, ResearchClaim.model_validate(c), i)
            for i, c in enumerate(payload["claims"])
        ]
    except (ValueError, TypeError, KeyError):
        errors.append("CLAIMS_MISSING_OR_INVALID")
    if snapshot.conflicts:
        errors.append("CONFLICTING_SNAPSHOT")
    if any(snapshot.coverage.get(f) != "available" for f in ("quote", "overview")):
        errors.append("CORE_EVIDENCE_MISSING")
    if any(c.status != "matches_snapshot" for c in claims):
        errors.append("MATERIAL_CLAIM_UNVERIFIED")
    report_hash = digest(report)
    return ResearchDossier(
        dossier_id="dossier_"
        + digest([snapshot.snapshot_id, snapshot.manifest_hash, report_hash]),
        snapshot_id=snapshot.snapshot_id,
        manifest_hash=snapshot.manifest_hash,
        run_id=snapshot.run_id,
        symbol=snapshot.symbol,
        report_hash=report_hash,
        claims=claims,
        errors=errors,
    )
