"""Evidence-bound valuation and applicability checks; missing facts never get invented defaults."""

from datetime import date

from ...database.repositories.evidence_repository import (
    EvidenceRepository,
    EvidenceStorage,
)
from ...models.evidence import EvidenceSnapshot
from ...models.research_strategy import StrategyReview, ValuationInput, ValuationResult
from ..evidence.identity import digest, same_value
from ..portfolio_risk.calendar import completed_session, sessions
from .calculators import dcf, peer_pe


class MissingInput(ValueError):
    pass


def _text(snapshot: EvidenceSnapshot, metric: str) -> str:
    rows = [
        r for r in snapshot.records if r.metric == metric and r.quality == "available"
    ]
    if not rows or not all(isinstance(r.value, str) for r in rows):
        raise MissingInput("IDENTITY_UNAVAILABLE:" + metric)
    if len({r.value for r in rows}) != 1:
        raise MissingInput("IDENTITY_CONFLICT:" + metric)
    return str(rows[0].value)


def applicable(snapshot: EvidenceSnapshot) -> None:
    if _text(snapshot, "instrument.type") != "EQUITY":
        raise MissingInput("INSTRUMENT_INAPPLICABLE")
    if _text(snapshot, "instrument.country") != "United States":
        raise MissingInput("COUNTRY_INAPPLICABLE")
    if _text(snapshot, "instrument.sector").casefold() in (
        "financial services",
        "financials",
    ):
        raise MissingInput("FINANCIAL_SECTOR_INAPPLICABLE")
    industry = _text(snapshot, "instrument.industry").casefold()
    if "bank" in industry or "insurance" in industry:
        raise MissingInput("INDUSTRY_INAPPLICABLE")


def select(
    snapshot: EvidenceSnapshot,
    metric: str,
    unit: str,
    period: str = "annual",
    end: date | None = None,
    age_allowance_days: int = 0,
) -> ValuationInput:
    contract = snapshot.strategy_contract
    if contract is None:
        raise MissingInput("STRATEGY_UNCONFIRMED")
    rows = [
        r
        for r in snapshot.records
        if r.metric == metric
        and r.period == period
        and (period == "session" or r.adapter_version == "idq-005@1")
    ]
    if not rows:
        raise MissingInput("MISSING:" + metric)
    dated = [r for r in rows if r.period_end and (end is None or r.period_end == end)]
    if not dated:
        raise MissingInput("PERIOD_UNAVAILABLE:" + metric)
    latest = max(r.period_end for r in dated if r.period_end is not None)
    rows = [r for r in dated if r.period_end == latest]
    if any(r.unit != unit for r in rows):
        raise MissingInput("UNIT_MISMATCH:" + metric)
    if any(r.quality != "available" or not isinstance(r.value, float) for r in rows):
        raise MissingInput("INPUT_UNAVAILABLE:" + metric)
    if not all(same_value(rows[0].value, r.value) for r in rows):
        raise MissingInput("CONFLICTING_INPUT:" + metric)
    conflicted = {e for ids in snapshot.conflicts.values() for e in ids}
    if any(r.evidence_id in conflicted for r in rows):
        raise MissingInput("CONFLICTING_INPUT:" + metric)
    if latest > snapshot.requested_as_of.date():
        raise MissingInput("FUTURE_INPUT:" + metric)
    if any(r.published_at and r.published_at > snapshot.requested_as_of for r in rows):
        raise MissingInput("FUTURE_PUBLICATION:" + metric)
    if snapshot.mode == "strict_historical" and any(
        r.point_in_time_status != "verified" for r in rows
    ):
        raise MissingInput("HISTORICAL_PIT_UNPROVEN")
    if period == "session":
        allowed = sessions(
            completed_session(snapshot.requested_as_of),
            contract.parameters.max_price_lag_sessions + 1,
        )
        if latest not in allowed:
            raise MissingInput("STALE_PRICE")
    elif (
        snapshot.requested_as_of.date() - latest
    ).days > contract.parameters.max_financial_age_days + age_allowance_days:
        raise MissingInput("STALE_FINANCIAL:" + metric)
    row = sorted(rows, key=lambda r: r.evidence_id)[0]
    return ValuationInput(
        snapshot_id=snapshot.snapshot_id,
        evidence_id=row.evidence_id,
        symbol=row.symbol,
        metric=metric,
        value=float(row.value or 0),
        unit=unit,
        period=period,
        period_end=latest,
    )


async def evaluate(db: EvidenceStorage, snapshot: EvidenceSnapshot) -> StrategyReview:
    contract = snapshot.strategy_contract
    if contract is None:
        raise MissingInput("STRATEGY_UNCONFIRMED")
    errors = []
    if snapshot.policy_revision != contract.cost_policy_revision:
        errors.append("COST_POLICY_REVISION_MISMATCH")
    values = []
    try:
        applicable(snapshot)
    except MissingInput as error:
        errors.append(str(error))
    try:
        select(snapshot, "price.close_reference", "USD", "session")
    except MissingInput as error:
        errors.append(str(error))
    repository = EvidenceRepository(db)
    for method in contract.parameters.methods:
        if errors:
            values.append(
                ValuationResult(
                    method=method, status="inapplicable", reasons=list(errors)
                )
            )
            continue
        try:
            if method == "peer_pe_annual@1":
                eps = select(snapshot, "eps", "USD/share")
                peer_rows = []
                declared = [
                    s for s in contract.parameters.peer_symbols if s != snapshot.symbol
                ]
                if set(declared) != set(snapshot.strategy_peers):
                    raise MissingInput("PEER_SET_MISMATCH")
                for symbol in declared:
                    peer = await repository.get(snapshot.strategy_peers[symbol])
                    if (
                        peer.run_id != snapshot.run_id
                        or peer.strategy_version != contract.version_id
                        or peer.symbol != symbol
                        or peer.requested_as_of != snapshot.requested_as_of
                    ):
                        raise MissingInput("PEER_SCOPE_MISMATCH")
                    applicable(peer)
                    if _text(peer, "instrument.industry") != _text(
                        snapshot, "instrument.industry"
                    ):
                        raise MissingInput("PEER_INDUSTRY_MISMATCH")
                    peer_rows.append(
                        (
                            select(peer, "price.close_reference", "USD", "session"),
                            select(peer, "eps", "USD/share", end=eps.period_end),
                        )
                    )
                result = peer_pe(eps, peer_rows)
            else:
                cfo = select(snapshot, "operating_cash_flow", "USD")
                selected = [
                    select(snapshot, m, u, end=cfo.period_end)
                    for m, u in [
                        ("capital_expenditure", "USD"),
                        ("interest_expense", "USD"),
                        ("total_debt", "USD"),
                        ("cash", "USD"),
                        ("diluted_shares", "shares"),
                    ]
                ]
                capex, interest, debt, cash, shares = selected
                result = dcf(
                    cfo, capex, interest, debt, cash, shares, contract.parameters
                )
            values.append(result)
        except (ValueError, OverflowError) as error:
            # Only our bounded reason codes escape; never raw provider text.
            reason = (
                str(error)
                if isinstance(error, MissingInput)
                else "VALUATION_INPUT_INVALID"
            )
            values.append(
                ValuationResult(method=method, status="unavailable", reasons=[reason])
            )
    # Mandate coverage is broader than a single valuation method. A usable PE
    # does not replace cash-flow/debt evidence required for fundamental research.
    for metric, unit in [
        ("eps", "USD/share"),
        ("diluted_shares", "shares"),
        ("revenue", "USD"),
        ("net_income", "USD"),
        ("operating_cash_flow", "USD"),
        ("capital_expenditure", "USD"),
        ("total_debt", "USD"),
        ("cash", "USD"),
    ]:
        try:
            select(snapshot, metric, unit)
        except MissingInput as error:
            errors.append("REQUIRED_" + str(error))
    errors.extend(reason for v in values for reason in v.reasons)
    params = contract.parameters
    monitoring = [
        f"Review at the next published financial report, and no later than {contract.horizon} {contract.horizon_unit}.",
        f"Annual diluted EPS decline >= {params.earnings_decline_fraction:.6g} requires thesis review, not automatic selling.",
        f"Net debt / positive FCFF proxy > {params.debt_to_fcf_limit:.6g} requires review; undefined ratio is missing evidence.",
        f"Price discount to an applicable model estimate below {params.valuation_discount:.6g} requires review; not an entry/stop/target rule.",
    ]
    from .monitoring import checks

    review = StrategyReview(
        review_id="",
        contract=contract,
        symbol=snapshot.symbol,
        snapshot_id=snapshot.snapshot_id,
        as_of=snapshot.requested_as_of,
        status=(
            "inapplicable"
            if any("INAPPLICABLE" in e for e in errors)
            else "insufficient_evidence" if errors else "research_only"
        ),
        errors=sorted(set(errors)),
        valuations=values,
        monitoring=monitoring,
        checks=checks(snapshot, values),
        prompt_versions={},
    )
    review.review_id = "strategy_review_" + digest(review.model_dump(mode="json"))
    return review
