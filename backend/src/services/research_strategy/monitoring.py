"""Deterministic review flags, never automatic buys/sells; unavailable is not a passed check."""

from ...models.evidence import EvidenceSnapshot
from ...models.research_strategy import MonitoringCheck, ValuationResult
from .evaluation import MissingInput, select


def checks(
    snapshot: EvidenceSnapshot, valuations: list[ValuationResult]
) -> list[MonitoringCheck]:
    contract = snapshot.strategy_contract
    if contract is None:
        return []
    p = contract.parameters
    out = []
    try:
        current = select(snapshot, "eps", "USD/share")
        dates = {
            r.period_end
            for r in snapshot.records
            if r.metric == "eps"
            and r.period == "annual"
            and r.period_end
            and r.period_end < current.period_end
        }
        if not dates:
            raise MissingInput("Prior annual EPS unavailable")
        if not 300 <= (current.period_end - max(dates)).days <= 430:
            raise MissingInput("Non-comparable fiscal year spacing")
        prior = select(
            snapshot, "eps", "USD/share", end=max(dates), age_allowance_days=366
        )
        if prior.value <= 0:
            raise MissingInput("Prior nonpositive EPS is not a percentage baseline")
        decline = 1 - current.value / prior.value
        out.append(
            MonitoringCheck(
                rule="earnings_decline",
                status=(
                    "triggered"
                    if decline >= p.earnings_decline_fraction
                    else "not_triggered"
                ),
                value=decline,
                threshold=p.earnings_decline_fraction,
                evidence_ids=[current.evidence_id, prior.evidence_id],
                reason="Current vs preceding annual diluted EPS; no source-truth/PIT certification.",
            )
        )
    except ValueError:
        out.append(
            MonitoringCheck(
                rule="earnings_decline",
                status="unavailable",
                value=None,
                threshold=p.earnings_decline_fraction,
                reason="Comparable positive prior EPS is unavailable.",
            )
        )
    model = next(
        (
            v
            for v in valuations
            if v.method == "fcff_proxy_dcf@1" and v.status == "available"
        ),
        None,
    )
    if model:
        inputs = {i.metric: i for i in model.inputs}
        fcff = (
            inputs["operating_cash_flow"].value
            + inputs["interest_expense"].value * (1 - p.tax_rate)
            - inputs["capital_expenditure"].value
        )
        ratio = (inputs["total_debt"].value - inputs["cash"].value) / fcff
        out.append(
            MonitoringCheck(
                rule="debt_to_fcf",
                status="triggered" if ratio > p.debt_to_fcf_limit else "not_triggered",
                value=ratio,
                threshold=p.debt_to_fcf_limit,
                evidence_ids=[i.evidence_id for i in model.inputs],
                reason="Net debt / positive modeled FCFF proxy, not an audited ratio.",
            )
        )
    else:
        out.append(
            MonitoringCheck(
                rule="debt_to_fcf",
                status="unavailable",
                value=None,
                threshold=p.debt_to_fcf_limit,
                reason="Applicable positive FCFF proxy is unavailable.",
            )
        )
    for valuation in valuations:
        result = None
        ids = []
        try:
            price = select(snapshot, "price.close_reference", "USD", "session")
            if (
                valuation.status == "available"
                and valuation.per_share_usd is not None
                and valuation.per_share_usd > 0
            ):
                result = 1 - price.value / valuation.per_share_usd
                ids = [price.evidence_id, *[i.evidence_id for i in valuation.inputs]]
        except ValueError:
            pass
        out.append(
            MonitoringCheck(
                rule="valuation_discount:" + valuation.method,
                status=(
                    "unavailable"
                    if result is None
                    else (
                        "triggered"
                        if result < p.valuation_discount
                        else "not_triggered"
                    )
                ),
                value=result,
                threshold=p.valuation_discount,
                evidence_ids=ids,
                reason="Discount to this conditional model estimate only; methods are not averaged.",
            )
        )
    return out
