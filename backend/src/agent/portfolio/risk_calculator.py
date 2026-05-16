"""Deterministic portfolio risk calculator (W2.5).

Why this exists:
  Phase2's prior portfolio_assessment was free-form LLM prose — sector
  concentration, beta exposure, cash %, correlation were all left to
  the model to "feel out". The PM/quant reviewer flagged this:
  Phase2 ≠ portfolio optimizer when there's no math behind it.
  This module computes the hard numbers separately and the W2.6 wiring
  injects them into the Phase2 prompt as constraints the LLM must
  reason against, not invent.

What it computes (per call):
  sector_exposure         {sector: {dollars, pct_of_equity}}
  beta_weighted_exposure  Σ(weight_i * beta_i)  (≈ 1 means market-like)
  cash_pct                cash / (cash + sum(market_value))
  position_concentration_hhi  Herfindahl–Hirschman Index of weights
  correlation_matrix      symmetric n×n dict[sym][sym] = 60d return corr
  portfolio_sigma         √(wᵀ Σ w) annualised σ from the daily Σ matrix
  largest_position        (symbol, pct)

Inputs:
  - holdings: list of Holding-like rows with .symbol/.quantity/.current_price
  - cash: float
  - fetch_meta(sym) -> {sector, beta} (callable; tests can pass a static dict)
  - fetch_returns(sym) -> pd.Series of daily returns (last 60 trading days)

The two fetcher callables are abstract so the module stays pure for
testing. In production they wrap yfinance.Ticker.info / .history.

Failure mode:
  - Missing sector for a symbol → bucketed under "Unknown" (not dropped).
  - Missing beta → treated as 1.0 (market-neutral assumption) and the
    `assumed_beta_for` list reports which symbols we filled.
  - Fewer than 30 days of return data for any symbol → that symbol is
    omitted from the correlation matrix, and `correlation_excluded`
    lists the omissions; portfolio_sigma is still computed on the
    remaining set.
  - Empty holdings → returns a sentinel dict with all metrics None and
    sets `error="no_positions"`. Caller decides how to render.
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

import structlog

logger = structlog.get_logger(__name__)


class SymbolMeta(TypedDict, total=False):
    sector: str | None
    beta: float | None


MetaFetcher = Callable[[str], Awaitable[SymbolMeta]]
ReturnsFetcher = Callable[[str], Awaitable[list[float]]]


# ---------------------------------------------------------------------------
# Helpers (pure)
# ---------------------------------------------------------------------------


def _safe_market_value(h: Any) -> float:
    """Holding.market_value can be None when current_price is missing.
    Recompute from quantity * current_price as best-effort fallback."""
    mv = getattr(h, "market_value", None)
    if isinstance(mv, (int, float)) and mv > 0:
        return float(mv)
    qty = float(getattr(h, "quantity", 0) or 0)
    px = float(getattr(h, "current_price", 0) or 0)
    return qty * px


def _hhi(weights: list[float]) -> float:
    """Herfindahl-Hirschman Index. Weights sum to 1. Pure single-stock
    portfolio = 1.0; equal n positions = 1/n."""
    return sum(w * w for w in weights)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def _corr(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    mx, my = _mean(xs), _mean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys, strict=True))
    sx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    sy = math.sqrt(sum((b - my) ** 2 for b in ys))
    if sx == 0 or sy == 0:
        return 0.0
    return num / (sx * sy)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


_MIN_RETURNS_FOR_CORR = 30
_TRADING_DAYS_PER_YEAR = 252


async def compute_portfolio_risk(
    holdings: list[Any],
    cash: float,
    fetch_meta: MetaFetcher,
    fetch_returns: ReturnsFetcher | None = None,
) -> dict[str, Any]:
    """Run the full risk profile. Returns a JSON-friendly dict.

    `fetch_returns` is optional — when omitted, correlation_matrix and
    portfolio_sigma are reported as None and `correlation_excluded`
    lists every symbol with reason="returns_fetcher_disabled".
    """
    if not holdings:
        return {
            "error": "no_positions",
            "sector_exposure": {},
            "beta_weighted_exposure": None,
            "cash_pct": 1.0 if cash > 0 else 0.0,
            "position_concentration_hhi": None,
            "correlation_matrix": None,
            "portfolio_sigma_annualised": None,
            "largest_position": None,
            "assumed_beta_for": [],
            "correlation_excluded": [],
        }

    # ---- Position weights (vs total equity = cash + sum mv) -------------
    mv_by_sym: dict[str, float] = {h.symbol: _safe_market_value(h) for h in holdings}
    invested = sum(mv_by_sym.values())
    total_equity = invested + max(0.0, cash)
    cash_pct = (cash / total_equity) if total_equity > 0 else 0.0

    weights_by_sym: dict[str, float] = {
        s: (v / total_equity if total_equity > 0 else 0.0) for s, v in mv_by_sym.items()
    }
    # Rank
    largest_sym, largest_w = max(
        weights_by_sym.items(), key=lambda kv: kv[1], default=("", 0.0)
    )
    hhi = _hhi(list(weights_by_sym.values()))

    # ---- Sector + beta lookup -------------------------------------------
    sector_dollars: dict[str, float] = {}
    betas: dict[str, float] = {}
    assumed_beta_for: list[str] = []
    for h in holdings:
        try:
            meta = await fetch_meta(h.symbol)
        except Exception as e:
            logger.warning("risk_meta_fetch_failed", symbol=h.symbol, error=str(e))
            meta = {}
        sector = meta.get("sector") or "Unknown"
        sector_dollars[sector] = sector_dollars.get(sector, 0.0) + mv_by_sym[h.symbol]
        beta = meta.get("beta")
        if not isinstance(beta, (int, float)):
            betas[h.symbol] = 1.0
            assumed_beta_for.append(h.symbol)
        else:
            betas[h.symbol] = float(beta)

    sector_exposure = {
        sec: {
            "dollars": round(d, 2),
            "pct_of_equity": round(d / total_equity, 4) if total_equity > 0 else 0.0,
        }
        for sec, d in sector_dollars.items()
    }
    beta_weighted_exposure = sum(
        weights_by_sym[s] * betas.get(s, 1.0) for s in weights_by_sym
    )

    # ---- Correlation + portfolio sigma ---------------------------------
    correlation_matrix: dict[str, dict[str, float]] | None = None
    portfolio_sigma: float | None = None
    correlation_excluded: list[dict[str, str]] = []

    if fetch_returns is None:
        correlation_excluded = [
            {"symbol": s, "reason": "returns_fetcher_disabled"} for s in mv_by_sym
        ]
    else:
        returns_by_sym: dict[str, list[float]] = {}
        for sym in mv_by_sym:
            try:
                rs = await fetch_returns(sym)
            except Exception as e:
                logger.warning("risk_returns_fetch_failed", symbol=sym, error=str(e))
                rs = []
            if len(rs) >= _MIN_RETURNS_FOR_CORR:
                returns_by_sym[sym] = list(rs)
            else:
                correlation_excluded.append(
                    {
                        "symbol": sym,
                        "reason": f"insufficient_history_{len(rs)}d",
                    }
                )

        if returns_by_sym:
            syms = list(returns_by_sym.keys())
            # truncate every series to the shortest length so corr is well-defined
            min_n = min(len(returns_by_sym[s]) for s in syms)
            r_trunc = {s: returns_by_sym[s][-min_n:] for s in syms}
            correlation_matrix = {
                a: {b: round(_corr(r_trunc[a], r_trunc[b]), 4) for b in syms}
                for a in syms
            }

            # Portfolio sigma_daily = sqrt(wᵀ Σ w) on the corr-included
            # subset; renormalise weights within that subset so the
            # number is interpretable when some symbols are excluded.
            included_w = {s: weights_by_sym[s] for s in syms}
            wsum = sum(included_w.values())
            if wsum > 0:
                w = {s: included_w[s] / wsum for s in syms}
                stdev_d = {s: _stdev(r_trunc[s]) for s in syms}
                # σ_p² = ΣΣ w_i w_j σ_i σ_j ρ_ij
                var_d = 0.0
                for a in syms:
                    for b in syms:
                        var_d += (
                            w[a]
                            * w[b]
                            * stdev_d[a]
                            * stdev_d[b]
                            * correlation_matrix[a][b]
                        )
                if var_d > 0:
                    portfolio_sigma = round(
                        math.sqrt(var_d) * math.sqrt(_TRADING_DAYS_PER_YEAR), 4
                    )

    return {
        "total_equity": round(total_equity, 2),
        "cash": round(cash, 2),
        "cash_pct": round(cash_pct, 4),
        "invested_value": round(invested, 2),
        "position_count": len(holdings),
        "sector_exposure": sector_exposure,
        "beta_weighted_exposure": round(beta_weighted_exposure, 4),
        "position_concentration_hhi": round(hhi, 4),
        "largest_position": (
            {"symbol": largest_sym, "weight": round(largest_w, 4)}
            if largest_sym
            else None
        ),
        "correlation_matrix": correlation_matrix,
        "portfolio_sigma_annualised": portfolio_sigma,
        "assumed_beta_for": assumed_beta_for,
        "correlation_excluded": correlation_excluded,
    }


def render_risk_block_for_prompt(risk: dict[str, Any]) -> str:
    """Compact markdown rendering used to inject into the Phase2 prompt
    (W2.6). Numbers only; no narrative — that's the LLM's job."""
    if risk.get("error") == "no_positions":
        return "## Portfolio Risk\n\n_No positions; nothing to compute._\n"

    sec_lines = "\n".join(
        f"  - {sec}: ${v['dollars']:,.0f} ({v['pct_of_equity'] * 100:.1f}%)"
        for sec, v in sorted(
            risk.get("sector_exposure", {}).items(),
            key=lambda kv: kv[1]["pct_of_equity"],
            reverse=True,
        )
    )
    beta_w = risk.get("beta_weighted_exposure")
    sigma = risk.get("portfolio_sigma_annualised")
    largest = risk.get("largest_position") or {}
    lines = [
        "## Portfolio Risk (deterministic, hard constraints)",
        "",
        f"- total_equity: ${risk.get('total_equity', 0):,.2f}",
        f"- cash_pct: {risk.get('cash_pct', 0) * 100:.2f}%",
        f"- position_count: {risk.get('position_count', 0)}",
        f"- largest_position: {largest.get('symbol', '?')} "
        f"({(largest.get('weight') or 0) * 100:.2f}%)",
        f"- position_concentration_hhi: {risk.get('position_concentration_hhi', 0):.4f}  "
        "(0=spread; 1=single name; >0.25 considered concentrated)",
        f"- beta_weighted_exposure: {beta_w if beta_w is not None else 'n/a'}  "
        "(>1.0 = portfolio more volatile than SPY)",
        f"- portfolio_sigma_annualised: {sigma if sigma is not None else 'n/a'}  "
        "(annualised σ; e.g. 0.30 means ~30% yearly vol)",
        "",
        "### Sector exposure",
        sec_lines or "  - (none)",
    ]
    if risk.get("assumed_beta_for"):
        lines.append("")
        lines.append(
            f"_⚠ Beta assumed = 1.0 (data unavailable) for: "
            f"{', '.join(risk['assumed_beta_for'])}_"
        )
    if risk.get("correlation_excluded"):
        excl = ", ".join(
            f"{e['symbol']} ({e['reason']})" for e in risk["correlation_excluded"]
        )
        lines.append(f"_⚠ Correlation excluded: {excl}_")
    return "\n".join(lines) + "\n"
