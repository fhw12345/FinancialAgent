"""Build non-actionable assessments from untrusted research/proposals."""

import hashlib
import json
import math
import re
from typing import Any

from pydantic import ValidationError

from ...core.utils.date_utils import utcnow
from ...core.version import BACKEND_VERSION
from ...models.decision_assessment import (
    AssessmentReason,
    DecisionAssessment,
    DraftProposal,
    Readiness,
    SymbolAssessment,
)
from ...models.portfolio_risk import PortfolioRiskReview
from ...shared.sanitizers import sanitize_text

PRIORITY: dict[Readiness, int] = {
    "research_only": 0,
    "needs_review": 1,
    "insufficient_evidence": 2,
    "blocked": 3,
}
MESSAGES = {
    "STAGE_A_ONLY": "Research only: full investment policy, point-in-time evidence, strategy and approval integration remain pending; risk checks alone grant no eligibility.",
    "RESEARCH_MISSING": "Required symbol research is missing.",
    "CHECK_UNAVAILABLE": "Research consistency check did not complete.",
    "CONSISTENCY_VIOLATION": "Research contains unresolved consistency violations.",
    "DATA_DEGRADED": "Research reports unavailable or degraded source data.",
    "QUOTE_UNAVAILABLE": "No usable quote is available; no price was invented.",
    "INVALID_PROPOSAL": "The model draft does not satisfy the strict write contract.",
    "SYMBOL_NOT_AUTHORIZED": "The model introduced a symbol outside this request.",
    "DUPLICATE_PROPOSAL": "Multiple model drafts target the same symbol.",
    "UNSUPPORTED_EXPOSURE": "A SELL requires a known current long holding; shorts are unsupported.",
    "DECISION_UNAVAILABLE": "Decision generation did not produce a usable result.",
    "PORTFOLIO_RISK_UNAVAILABLE": "Full account risk data is unavailable; no subset risk clearance.",
    "ALLOCATION_BLOCKED": "The whole-batch risk/allocation preview was rejected; see its constraints.",
}


def reason(code: Any) -> AssessmentReason:
    return AssessmentReason(code=code, message=MESSAGES[code])


def normalize_proposal(raw: dict[str, Any]) -> DraftProposal:
    if any(key in raw for key in ("ready", "readiness", "approved", "actionable")):
        raise ValueError("Model cannot set authoritative eligibility")
    action = str(raw.get("decision", "")).upper()
    return DraftProposal.model_validate(
        {
            "symbol": str(raw.get("symbol", "")).upper(),
            "proposed_action": action,
            "intent": raw.get("intent")
            or {"BUY": "open_long", "SELL": "close_long", "HOLD": "hold"}.get(action),
            "size_percent": raw.get("position_size_percent"),
            "entry": raw.get("entry_price"),
            "stop": raw.get("stop_loss"),
            "target": raw.get("take_profit"),
            "reasoning": sanitize_text(str(raw.get("reasoning_summary") or "")),
        }
    )


def build_assessment(
    *,
    request_key: str,
    source: str,
    symbols: list[str],
    proposals: list[dict[str, Any]],
    research: dict[str, str] | None = None,
    quality: dict[str, dict[str, Any]] | None = None,
    quotes: dict[str, float | None] | None = None,
    holdings: list[str] | None = None,
    run_id: str | None = None,
    portfolio_risk: PortfolioRiskReview | None = None,
) -> DecisionAssessment:
    expected = list(dict.fromkeys(symbol.upper() for symbol in symbols))
    if not expected or any(
        not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,14}", s) for s in expected
    ):
        raise ValueError("A validated request symbol set is required")
    research, quality = research or {}, quality or {}
    held = {symbol.upper() for symbol in holdings} if holdings is not None else None
    grouped: dict[str, list[dict[str, Any]]] = {}
    for raw in proposals:
        symbol = str(raw.get("symbol", "")).upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,14}", symbol):
            symbol = "UNKNOWN"
        grouped.setdefault(symbol, []).append(raw)
    results = []
    for symbol in list(dict.fromkeys([*expected, *grouped])):
        readiness: Readiness = "research_only"
        reasons = [reason("STAGE_A_ONLY")]
        text = sanitize_text(research.get(symbol, ""))
        fields = quality.get(symbol, {})
        draft = None
        if not text.strip():
            readiness = "insufficient_evidence"
            reasons.append(reason("RESEARCH_MISSING"))
        if fields.get("degraded_fields"):
            readiness = "insufficient_evidence"
            reasons.append(reason("DATA_DEGRADED"))
        violations = fields.get("consistency_violations") or []
        unavailable = fields.get("check_unavailable") or any(
            v.get("code") == "CHECK_UNAVAILABLE" for v in violations
        )
        if unavailable:
            readiness = "needs_review"
            reasons.append(reason("CHECK_UNAVAILABLE"))
        elif violations or fields.get("consistency_passed") is False:
            readiness = "insufficient_evidence"
            reasons.append(reason("CONSISTENCY_VIOLATION"))
        if fields.get("decision_unavailable"):
            readiness = "needs_review"
            reasons.append(reason("DECISION_UNAVAILABLE"))
        if quotes is not None:
            quote = quotes.get(symbol)
            if (
                isinstance(quote, bool)
                or not isinstance(quote, (float, int))
                or not math.isfinite(quote)
                or quote <= 0
            ):
                readiness = "insufficient_evidence"
                reasons.append(reason("QUOTE_UNAVAILABLE"))
        entries = grouped.get(symbol, [])
        if len(entries) > 1:
            readiness = "blocked"
            reasons.append(reason("DUPLICATE_PROPOSAL"))
        elif entries:
            try:
                draft = normalize_proposal(entries[0])
            except (ValueError, ValidationError):
                readiness = "blocked"
                reasons.append(reason("INVALID_PROPOSAL"))
            if (
                draft
                and draft.proposed_action == "SELL"
                and (held is None or symbol not in held)
            ):
                readiness = "blocked"
                reasons.append(reason("UNSUPPORTED_EXPOSURE"))
        if symbol not in expected:
            readiness = "blocked"
            reasons.append(reason("SYMBOL_NOT_AUTHORIZED"))
        codes = {r.code for r in reasons}
        readiness = (
            "blocked"
            if codes
            & {
                "INVALID_PROPOSAL",
                "SYMBOL_NOT_AUTHORIZED",
                "DUPLICATE_PROPOSAL",
                "UNSUPPORTED_EXPOSURE",
            }
            else (
                "insufficient_evidence"
                if codes
                & {
                    "RESEARCH_MISSING",
                    "DATA_DEGRADED",
                    "QUOTE_UNAVAILABLE",
                    "CONSISTENCY_VIOLATION",
                }
                else (
                    "needs_review"
                    if codes & {"CHECK_UNAVAILABLE", "DECISION_UNAVAILABLE"}
                    else "research_only"
                )
            )
        )
        if portfolio_risk:
            if portfolio_risk.current.status != "complete":
                reasons.append(reason("PORTFOLIO_RISK_UNAVAILABLE"))
                if readiness != "blocked":
                    readiness = "insufficient_evidence"
            allocation = portfolio_risk.allocation
            if allocation and set(allocation.constraints) - {
                "POLICY_UNCONFIRMED",
                "CURRENT_RISK_UNAVAILABLE",
            }:
                reasons.append(reason("ALLOCATION_BLOCKED"))
                readiness = "blocked"
        results.append(
            SymbolAssessment(
                symbol=symbol,
                readiness=readiness,
                proposal=draft,
                research=text,
                exposure_context=(
                    "unknown" if held is None else "held" if symbol in held else "flat"
                ),
                reasons=reasons,
            )
        )
    # Bind both the normalized record and raw draft inputs to retry identity.
    # Raw drafts are hashed only: they are never returned or stored as payloads.
    payload = {
        "source": source,
        "symbols": expected,
        "results": [r.model_dump(mode="json") for r in results],
        "run_id": run_id,
        "portfolio_risk": (
            portfolio_risk.model_dump(mode="json") if portfolio_risk else None
        ),
        "proposals": proposals,
        "quotes": quotes,
        "holdings": sorted(held) if held is not None else None,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()
    assessment_id = (
        "assessment_"
        + hashlib.sha256(f"{source}:{request_key}".encode()).hexdigest()[:32]
    )
    return DecisionAssessment(
        assessment_id=assessment_id,
        request_key=request_key,
        input_hash=digest,
        run_id=run_id,
        source=source,
        created_at=utcnow(),
        backend_version=BACKEND_VERSION,
        portfolio_risk=portfolio_risk,
        readiness=max((r.readiness for r in results), key=lambda item: PRIORITY[item]),
        results=results,
    )
