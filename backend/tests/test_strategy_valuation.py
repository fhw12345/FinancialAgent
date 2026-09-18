"""ST-02…07: typed numeric oracles, missing-data behavior and no invented model probabilities."""

import pytest
from pydantic import ValidationError
from src.services.research_strategy.calculators import (
    peer_pe,
    dcf,
    enterprise_to_equity,
)
from src.models.research_strategy import Forecast, StrategyConclusion
from tests.strategy_fixtures import parameters, value


def dcf_inputs():
    return [
        value("operating_cash_flow", 150),
        value("capital_expenditure", 50),
        value("interest_expense", 10),
        value("total_debt", 100),
        value("cash", 20),
        value("diluted_shares", 10, "shares"),
    ]


def test_pe_known_multiple_is_100_per_share_not_ratio_20():
    result = peer_pe(
        value("eps", 5, "USD/share"),
        [
            (
                value("price", 100, period="session", symbol="MSFT"),
                value("eps", 5, "USD/share", symbol="MSFT"),
            )
        ],
    )
    assert result.peer_multiple == 20 and result.per_share_usd == 100
    assert result.enterprise_value is None and result.interpretation.startswith(
        "conditional"
    )


def test_no_eps_peers_or_positive_earnings_no_fabricated_value():
    assert peer_pe(value("eps", 5, "USD/share"), []).status == "unavailable"
    result = peer_pe(
        value("eps", -1, "USD/share"),
        [(value("price", 100, period="session"), value("eps", 5, "USD/share"))],
    )
    assert result.status == "inapplicable" and result.per_share_usd is None


def test_dcf_discount_monotonic_and_exact_enterprise_equity_bridge():
    inputs = dcf_inputs()
    low = dcf(*inputs, parameters(discount_rate=0.1))
    high = dcf(*inputs, parameters(discount_rate=0.2))
    assert low.enterprise_value > high.enterprise_value > 0
    assert low.equity_value == pytest.approx(low.enterprise_value - 80)
    assert low.per_share_usd == pytest.approx(low.equity_value / 10)
    assert enterprise_to_equity(1000, 200, 10) == (800, 80)
    with pytest.raises(ValidationError):
        parameters(terminal_growth=0.1, discount_rate=0.1)
    with pytest.raises(ValueError):
        enterprise_to_equity(100, 0, 0)


def test_units_and_periods_cannot_be_averaged_or_coerced():
    inputs = dcf_inputs()
    inputs[0] = value("operating_cash_flow", 150, "USD million")
    with pytest.raises(ValueError, match="UNIT_MISMATCH"):
        dcf(*inputs, parameters())
    with pytest.raises(ValueError):
        parameters(methods=["peer_pe_annual@1", "peer_pe_annual@1"])
    with pytest.raises(ValueError):
        parameters(discount_rate=float("nan"))
    with pytest.raises(ValueError):
        parameters(peer_symbols=["MSFT", "MSFT"])


def test_valuation_rejects_bad_period_sign_and_nonpositive_equity():
    from datetime import date

    inputs = dcf_inputs()
    inputs[0].period_end = date(2024, 12, 31)
    with pytest.raises(ValueError, match="FISCAL_PERIOD_MISMATCH"):
        dcf(*inputs, parameters())
    inputs = dcf_inputs()
    inputs[0].period = "quarter"
    with pytest.raises(ValueError, match="ANNUAL_INPUT_REQUIRED"):
        dcf(*inputs, parameters())
    inputs = dcf_inputs()
    inputs[1].value = -1.0
    with pytest.raises(ValueError, match="SIGN"):
        dcf(*inputs, parameters())
    inputs = dcf_inputs()
    inputs[0].value = 1.0
    assert dcf(*inputs, parameters()).status == "inapplicable"
    with pytest.raises(ValueError):
        enterprise_to_equity(100, 200, 10)
    with pytest.raises(ValueError):
        enterprise_to_equity(float("inf"), 0, 10)
    with pytest.raises(ValueError):
        peer_pe(
            value("eps", 5, "USD/share", period="quarter"),
            [(value("price", 100, period="session"), value("eps", 5, "USD/share"))],
        )


def test_subjective_scenarios_never_become_empirical_probabilities():
    assert Forecast(scenario="base", condition="If margins persist").probability is None
    with pytest.raises(ValueError):
        Forecast(
            scenario="base",
            condition="Pretend calibration",
            probability=0.8,
            probability_basis="empirical",
        )
    with pytest.raises(ValueError):
        StrategyConclusion(
            symbol="AAPL",
            stance="bullish",
            theses=[],
            scenarios=[],
            report_markdown="test",
            portfolio_action="BUY",
        )
