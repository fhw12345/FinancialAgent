"""Typed, deterministic model estimates; inputs/assumptions stay distinct and no formulas execute."""

import math
from statistics import median

from ...models.research_strategy import (
    StrategyParameters,
    ValuationInput,
    ValuationResult,
)


def _check(inputs: list[ValuationInput], units: list[str]) -> None:
    if len(inputs) != len(units) or any(
        v.unit != u for v, u in zip(inputs, units, strict=True)
    ):
        raise ValueError("UNIT_MISMATCH")
    if len({i.period_end for i in inputs if i.period != "session"}) > 1:
        raise ValueError("FISCAL_PERIOD_MISMATCH")


def peer_pe(
    eps: ValuationInput, peers: list[tuple[ValuationInput, ValuationInput]]
) -> ValuationResult:
    inputs = [eps, *[item for pair in peers for item in pair]]
    if not peers:
        return ValuationResult(
            method="peer_pe_annual@1",
            status="unavailable",
            reasons=["PEERS_MISSING"],
            inputs=inputs,
        )
    _check(inputs, ["USD/share", *["USD", "USD/share"] * len(peers)])
    if eps.value <= 0 or any(e.value <= 0 or p.value <= 0 for p, e in peers):
        return ValuationResult(
            method="peer_pe_annual@1",
            status="inapplicable",
            reasons=["NONPOSITIVE_EARNINGS_OR_PRICE"],
            inputs=inputs,
        )
    if any(i.period != "annual" for i in [eps, *[e for _, e in peers]]):
        raise ValueError("ANNUAL_EPS_REQUIRED")
    multiple = median(p.value / e.value for p, e in peers)
    return ValuationResult(
        method="peer_pe_annual@1",
        status="available",
        inputs=inputs,
        peer_multiple=multiple,
        per_share_usd=eps.value * multiple,
        assumptions={
            "peer_statistic": "median; no post-hoc exclusions",
            "basis": "annual diluted EPS, not TTM/forward EPS",
        },
    )


def enterprise_to_equity(
    enterprise: float, net_debt: float, shares: float
) -> tuple[float, float]:
    if (
        not all(math.isfinite(x) for x in (enterprise, net_debt, shares))
        or shares <= 0
        or enterprise <= 0
    ):
        raise ValueError("INVALID_ENTERPRISE_EQUITY_INPUT")
    equity = enterprise - net_debt
    if equity <= 0:
        raise ValueError("NONPOSITIVE_EQUITY_VALUE")
    return equity, equity / shares


def fcff_proxy(
    cfo: ValuationInput,
    capex: ValuationInput,
    interest: ValuationInput,
    tax_rate: float,
) -> float:
    _check([cfo, capex, interest], ["USD", "USD", "USD"])
    if any(v.period != "annual" for v in [cfo, capex, interest]):
        raise ValueError("ANNUAL_INPUT_REQUIRED")
    if capex.value < 0 or interest.value < 0 or not 0 <= tax_rate <= 1:
        raise ValueError("INVALID_FINANCIAL_INPUT_SIGN")
    proxy = cfo.value + interest.value * (1 - tax_rate) - capex.value
    if not math.isfinite(proxy):
        raise ValueError("NONFINITE_FCFF_PROXY")
    return proxy


def debt_to_fcff(
    cfo: ValuationInput,
    capex: ValuationInput,
    interest: ValuationInput,
    debt: ValuationInput,
    cash: ValuationInput,
    tax_rate: float,
) -> float:
    _check([cfo, capex, interest, debt, cash], ["USD"] * 5)
    if (
        debt.value < 0
        or cash.value < 0
        or debt.period != "annual"
        or cash.period != "annual"
    ):
        raise ValueError("INVALID_DEBT_INPUT")
    proxy = fcff_proxy(cfo, capex, interest, tax_rate)
    if proxy <= 0:
        raise ValueError("NONPOSITIVE_FCFF_PROXY")
    return (debt.value - cash.value) / proxy


def dcf(
    cfo: ValuationInput,
    capex: ValuationInput,
    interest: ValuationInput,
    debt: ValuationInput,
    cash: ValuationInput,
    shares: ValuationInput,
    params: StrategyParameters,
) -> ValuationResult:
    inputs = [cfo, capex, interest, debt, cash, shares]
    _check(inputs, ["USD", "USD", "USD", "USD", "USD", "shares"])
    if any(v.period != "annual" for v in inputs):
        raise ValueError("ANNUAL_INPUT_REQUIRED")
    if (
        capex.value < 0
        or interest.value < 0
        or debt.value < 0
        or cash.value < 0
        or shares.value <= 0
    ):
        raise ValueError("INVALID_FINANCIAL_INPUT_SIGN")
    if params.terminal_growth >= params.discount_rate:
        raise ValueError("INVALID_TERMINAL_GROWTH")
    fcff = fcff_proxy(cfo, capex, interest, params.tax_rate)
    assumptions = {
        "discount_rate": params.discount_rate,
        "growth_rate": params.growth_rate,
        "terminal_growth": params.terminal_growth,
        "tax_rate": params.tax_rate,
        "projection_years": float(params.projection_years),
        "basis": "CFO + interest*(1-tax) - capex: unlevering proxy, not audited FCFF",
        "dilution": "annual diluted-average shares held constant; future issuance unknown",
        "limitation": "accrual interest may differ from cash interest; tax assumption is user-declared",
    }
    if fcff <= 0:
        return ValuationResult(
            method="fcff_proxy_dcf@1",
            status="inapplicable",
            reasons=["NONPOSITIVE_FCFF_PROXY"],
            inputs=inputs,
            assumptions=assumptions,
        )
    projected = [
        fcff * (1 + params.growth_rate) ** year
        for year in range(1, params.projection_years + 1)
    ]
    terminal = (
        projected[-1]
        * (1 + params.terminal_growth)
        / (params.discount_rate - params.terminal_growth)
    )
    enterprise = (
        sum(
            v / (1 + params.discount_rate) ** year
            for year, v in enumerate(projected, 1)
        )
        + terminal / (1 + params.discount_rate) ** params.projection_years
    )
    equity, per_share = enterprise_to_equity(
        enterprise, debt.value - cash.value, shares.value
    )
    return ValuationResult(
        method="fcff_proxy_dcf@1",
        status="available",
        inputs=inputs,
        assumptions=assumptions,
        enterprise_value=enterprise,
        equity_value=equity,
        per_share_usd=per_share,
    )
