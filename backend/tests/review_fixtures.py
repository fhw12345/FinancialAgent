"""Synthetic outer storage/provider inputs. Production gates/calculators/commits stay real."""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

from src.database.repositories.decision_assessment_repository import (
    DecisionAssessmentRepository,
)
from src.database.repositories.holding_repository import HoldingRepository
from src.models.decision_review import (
    ConfirmReviewPolicy,
    ProposeReview,
    ReviewPolicyInput,
    ReviewTarget,
)
from src.models.evidence import EvidenceRecord
from src.models.holding import HoldingCreate
from src.models.portfolio_risk import PortfolioRiskReview
from src.models.research_strategy import StrategyConclusion, StrategyConclusions, Thesis
from src.services.decision_policy import (
    builder,
    control,
    policies,
    review_gate,
    review_projection,
    review_service,
)
from src.services.evidence import service as evidence
from src.services.evidence.context import evidence_scope
from src.services.portfolio_risk import service as risk
from src.services.portfolio_risk.calendar import sessions
from src.services.portfolio_risk.estimator import estimate
from src.services.research_strategy import service as strategy, store
from tests.evidence_fixtures import Database, claim_block
from tests.portfolio_risk_fixtures import asset, policy
from tests.strategy_evidence_fixtures import captured, save
from tests.strategy_fixtures import parameters

NOW = datetime(2026, 9, 18, 12, tzinfo=UTC)
SESSION = date(2026, 9, 17)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


def market_asset(symbol):
    return asset(symbol, dates=sessions(SESSION)).model_copy(
        update={"mark_session": SESSION}
    )


async def setup(
    monkeypatch,
    *,
    targets=None,
    limits=None,
    parameter_changes=None,
    cash=9000.0,
    quantity=10.0,
    prior_eps=4.0,
    financial_changes=None,
    model_policy=None,
):
    for module in (
        risk,
        store,
        policies,
        review_gate,
        review_projection,
        review_service,
    ):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(builder, "utcnow", lambda: NOW)
    monkeypatch.setattr(
        risk.provider,
        "fetch_asset",
        AsyncMock(side_effect=lambda symbol, session: market_asset(symbol)),
    )
    db = Database()
    db.now = NOW
    db.get_collection("user_settings").rows["local"] = {
        "_id": "local",
        "cash_balance": cash,
    }
    await HoldingRepository(db.get_collection("holdings")).create(
        holding_create=HoldingCreate(symbol="AAPL", quantity=quantity, avg_price=90.0)
    )
    costs = await risk.confirm_policy(db, policy(**(limits or {})).policy, 0)
    contract = store.active_version(
        await store.confirm(
            db,
            parameters(
                **{
                    "valuation_discount": 0.0,
                    "peer_symbols": ["AAPL", "MSFT"],
                    **(parameter_changes or {}),
                }
            ),
            0,
            "strategy-request",
            costs.revision,
        )
    )
    snapshot = await risk.capture(db, ["AAPL", "MSFT"])
    snaps = {}
    for symbol in ("AAPL", "MSFT"):
        snap = captured(symbol, contract).model_copy(
            update={
                "risk_snapshot_id": snapshot.snapshot_id,
                "freshness_policy": "strategy-contract@1",
                "strategy_peers": {
                    s: "snapshot_" + s
                    for s in contract.parameters.peer_symbols
                    if s != symbol
                },
            }
        )
        for row in snap.records:
            if row.metric in (financial_changes or {}):
                row.value = financial_changes[row.metric]
            row.family = (
                "quote"
                if row.metric.startswith("price.")
                else (
                    "cash_flow"
                    if row.metric in ("operating_cash_flow", "capital_expenditure")
                    else (
                        "balance_sheet"
                        if row.metric in ("total_debt", "cash")
                        else (
                            "overview"
                            if row.metric.startswith("instrument.")
                            else "income_statement"
                        )
                    )
                )
            )
        eps = next(r for r in snap.records if r.metric == "eps")
        snap.records.append(
            eps.model_copy(
                update={"value": prior_eps, "period_end": date(2024, 12, 31)}
            )
        )
        snap.records.append(
            EvidenceRecord(
                snapshot_id=snap.snapshot_id,
                symbol=symbol,
                instrument_id=symbol + "@NASDAQ:USD",
                family="ohlcv",
                metric="ohlcv.bar_count",
                value=60.0,
                unit="count",
                period="session",
                period_end=SESSION,
                fetched_at=NOW,
                provider="recorded",
            )
        )
        snap.coverage = {r.family: "available" for r in snap.records}
        save(db, snap)
        snaps[symbol] = snap
    with evidence_scope(snaps):
        reports = {
            s: "Synthetic conditional research. " + claim_block(s) for s in snaps
        }
    summary = await evidence.dossiers(db, snaps, reports)
    reviews = await strategy.reviews(db, snaps)
    strategy.apply_conclusions(
        reviews,
        snaps,
        StrategyConclusions(
            conclusions=[
                StrategyConclusion(
                    symbol=s,
                    stance="bullish",
                    theses=[
                        Thesis(
                            text="Synthetic thesis, not verified prose",
                            evidence_ids=[
                                next(
                                    r.evidence_id
                                    for r in snap.records
                                    if r.metric == "eps"
                                )
                            ],
                            monitoring_rule="earnings_decline",
                        )
                    ],
                    scenarios=[],
                    report_markdown="Conditional test estimate",
                )
                for s, snap in snaps.items()
            ]
        ),
    )
    for review in reviews.values():
        review.prompt_versions = {
            "strategy-fundamental": "strategy-fundamental@1",
            "strategy-conclusion": "strategy-conclusion@1",
        }
    source = await DecisionAssessmentRepository(
        db.get_collection("decision_assessments")
    ).assess_and_persist(
        request_key="review-source",
        source="portfolio",
        symbols=list(snaps),
        proposals=[],
        research=reports,
        quality={s: {"consistency_passed": True} for s in snaps},
        quotes={s: 100.0 for s in snaps},
        holdings=["AAPL"],
        run_id="run",
        portfolio_risk=PortfolioRiskReview(
            snapshot=snapshot, current=estimate(snapshot)
        ),
        evidence=summary,
        strategy=strategy.summary(reviews),
    )
    db.get_collection("agent_runs").rows["run"] = {
        "_id": "run",
        "run_id": "run",
        "status": "completed",
    }
    state = await control.read(db)
    await policies.confirm(
        db,
        ConfirmReviewPolicy(
            expected_revision=state.revision,
            expected_generation=state.generation,
            request_id="policy-request",
            confirm=True,
            policy=ReviewPolicyInput(
                risk_policy_revision=costs.revision,
                strategy_version=contract.version_id,
                allowed_symbols=["AAPL", "MSFT"],
                max_account_sigma=0.5,
                lifetime_minutes=60,
                acknowledged_contract="manual-target-paper-review@1",
                instrument_attestation="USD-US-nonfinancial-common-equities",
                evidence_acknowledgment="forward-close-not-truth-or-historical-PIT",
                **(model_policy or {}),
            ),
        ),
    )
    state = await control.read(db)
    request = ProposeReview(
        expected_revision=state.revision,
        expected_generation=state.generation,
        request_id="proposal-request",
        assessment_id=source.assessment_id,
        targets=[
            ReviewTarget(symbol=s, target_weight=w)
            for s, w in (targets or {"AAPL": 0.2}).items()
        ],
    )
    return db, request, source, snaps
