"""Revalidate sealed source membership and typed claims. Never certify prose/source truth."""

from datetime import datetime

from ...database.repositories.evidence_repository import (
    EvidenceConflict,
    EvidenceRepository,
    EvidenceStorage,
)
from ...models.decision_assessment import DecisionAssessment
from ...models.decision_review import GateReason, ReviewPolicyVersion, SymbolProof
from ...models.research_strategy import StrategyConclusions
from ..evidence.claims import build_dossier
from ..research_strategy.evaluation import evaluate, select
from ..research_strategy.service import apply_conclusions

REQUIRED = (
    ("eps", "USD/share"),
    ("diluted_shares", "shares"),
    ("revenue", "USD"),
    ("net_income", "USD"),
    ("operating_cash_flow", "USD"),
    ("capital_expenditure", "USD"),
    ("total_debt", "USD"),
    ("cash", "USD"),
)


def failure(code: str, symbol: str | None = None) -> GateReason:
    return GateReason(code=code, severity="insufficient_evidence", symbol=symbol)


async def validate(
    db: EvidenceStorage,
    source: DecisionAssessment,
    symbol: str,
    policy: ReviewPolicyVersion,
    now: datetime,
) -> tuple[SymbolProof | None, list[GateReason], datetime | None]:
    evidence, strategy, risk = source.evidence, source.strategy, source.portfolio_risk
    if evidence is None or strategy is None or risk is None:
        return None, [failure("BOUND_EVIDENCE_STRATEGY_RISK_REQUIRED", symbol)], None
    saved = [r for r in strategy.reviews if r.symbol == symbol]
    research = [r for r in source.results if r.symbol == symbol]
    if len(saved) != 1 or len(research) != 1:
        return None, [failure("SOURCE_SYMBOL_SCOPE_MISMATCH", symbol)], None
    review = saved[0]
    repository = EvidenceRepository(db)
    try:
        snapshot = await repository.get(review.snapshot_id)
        if (
            snapshot.snapshot_id not in evidence.snapshot_ids
            or snapshot.symbol != symbol
            or snapshot.run_id != source.run_id
            or snapshot.mode != "research"
            or snapshot.risk_snapshot_id != risk.snapshot.snapshot_id
            or snapshot.policy_revision != policy.policy.risk_policy_revision
            or snapshot.strategy_contract != review.contract
            or snapshot.strategy_version != policy.policy.strategy_version
            or review.contract.version_id != policy.policy.strategy_version
            or snapshot.requested_as_of > now
        ):
            return None, [failure("SEALED_SOURCE_SCOPE_MISMATCH", symbol)], None
        if any(
            snapshot.coverage.get(family) != "available"
            for family in (
                "quote",
                "overview",
                "ohlcv",
                "income_statement",
                "cash_flow",
                "balance_sheet",
            )
        ):
            return (
                None,
                [failure("REQUIRED_FUNDAMENTAL_COVERAGE_MISSING", symbol)],
                None,
            )
        dossier = build_dossier(snapshot, research[0].research)
        if dossier.dossier_id not in evidence.dossier_ids:
            return None, [failure("REPORT_DOSSIER_MISMATCH", symbol)], None
        stored = await repository.get_dossier(dossier.dossier_id)
        if stored != dossier or dossier.errors or not dossier.claims:
            return None, [failure("STRUCTURED_CLAIMS_UNVERIFIED", symbol)], None
        for identifier in snapshot.strategy_peers.values():
            peer = await repository.get(identifier)
            if (
                peer.risk_snapshot_id != risk.snapshot.snapshot_id
                or peer.policy_revision != snapshot.policy_revision
                or peer.mode != "research"
            ):
                return None, [failure("PEER_INPUT_SCOPE_MISMATCH", symbol)], None
        fresh = await evaluate(db, snapshot)
        if review.conclusion is None:
            return None, [failure("STRATEGY_CONCLUSION_REQUIRED", symbol)], None
        apply_conclusions(
            {symbol: fresh},
            {symbol: snapshot},
            StrategyConclusions(conclusions=[review.conclusion]),
        )
        reasons = []
        if (
            fresh.status != "research_only"
            or fresh.errors
            or review.errors
            or fresh.review_id != review.review_id
            or fresh.valuations != review.valuations
            or fresh.checks != review.checks
            or review.conclusion.stance == "unknown"
            or review.prompt_versions.get("strategy-fundamental")
            != "strategy-fundamental@1"
            or review.prompt_versions.get("strategy-conclusion")
            != "strategy-conclusion@1"
        ):
            reasons.append(failure("STRATEGY_REVALIDATION_FAILED", symbol))
        inputs = [i for value in fresh.valuations for i in value.inputs]
        inputs.extend(select(snapshot, metric, unit) for metric, unit in REQUIRED)
        if any(
            i.period != "session"
            and (now.date() - i.period_end).days
            > review.contract.parameters.max_financial_age_days
            for i in inputs
        ):
            reasons.append(failure("FINANCIAL_PERIOD_EXPIRED", symbol))
        return (
            SymbolProof(
                symbol=symbol,
                snapshot_id=snapshot.snapshot_id,
                manifest_hash=snapshot.manifest_hash,
                dossier_id=dossier.dossier_id,
                strategy_review_id=fresh.review_id,
                monitoring={c.rule: c.status for c in fresh.checks},
                unverified_context=[
                    "source_truth",
                    "free_prose",
                    "historical_PIT",
                    *[
                        family
                        for family in ("news", "filing")
                        if snapshot.coverage.get(family) != "available"
                    ],
                ],
            ),
            reasons,
            snapshot.requested_as_of,
        )
    except (EvidenceConflict, ValueError):
        # Availability/schema/manifest failures are explicit negatives, not successful
        # "consistency" checks. Transport/storage exceptions still propagate.
        return None, [failure("SEALED_INPUT_UNAVAILABLE_OR_INVALID", symbol)], None
