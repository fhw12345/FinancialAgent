"""Predeclared synthetic portfolio cases, not user limits or profitable-trade labels."""

from dataclasses import asdict, dataclass
from src.services.evidence.identity import digest


@dataclass(frozen=True)
class PortfolioCase:
    case_id: str
    cash: float
    quantity: float
    position_limit: float = 1.0
    sector_limit: float = 1.0
    cash_floor: float = 0.0
    fee_bps: float = 1.0
    slip_bps: float = 10.0
    may_open: bool = True
    may_exit: bool = True
    bearish: bool = False
    injection: bool = False
    negative: str | None = None


CASES = (
    PortfolioCase("cash-rich", 9000, 10, 0.3, 0.6, 0.2),
    PortfolioCase("concentrated", 3000, 70, 0.3, 0.6, 0.2),
    PortfolioCase("cash-poor", 100, 99),
    PortfolioCase("bearish", 5000, 50, bearish=True),
    PortfolioCase("fractional-costs", 2500, 0.3, 0.4, 0.6, 0.2, 25, 50),
    PortfolioCase(
        "injection",
        9000,
        10,
        0.3,
        0.6,
        0.2,
        may_open=False,
        may_exit=False,
        injection=True,
    ),
    PortfolioCase("disabled", 9000, 10, negative="disabled"),
    PortfolioCase("missing-evidence", 9000, 10, negative="missing"),
    PortfolioCase("inactive-strategy", 9000, 10, negative="strategy"),
)


def manifest():
    body = {
        "version": "model-portfolios@1",
        "max_calls": 6,
        "per_case_max_calls": 1,
        "model": "gpt-6-astra",
        "max_output_tokens": 4096,
        "max_seconds": 600,
        "inputs": "synthetic-sealed-research-not-live-research",
        "cases": [asdict(c) for c in CASES],
    }
    return {**body, "manifest_hash": digest(body)}


def case(identifier):
    found = next((c for c in CASES if c.case_id == identifier), None)
    if found is None:
        raise ValueError("Unknown registered portfolio case")
    return found
