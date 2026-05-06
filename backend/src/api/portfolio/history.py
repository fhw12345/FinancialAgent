"""
Portfolio history endpoint.

W5a: Alpaca live trading removed. Portfolio value time series is reconstructed
locally from current holdings × historical OHLCV bars (yfinance). Per-period
granularity:
  1D  → 5-minute bars over today's session
  1M  → daily bars over the last ~30 days
  1Y  → daily bars over the last ~12 months
  All → weekly bars over the last ~5 years

Caveat: ignores historical position changes — if you bought NVDA today but ask
for a 1Y view, NVDA is treated as held the whole year. Acceptable approximation
for a personal local tool; a more accurate version would replay user_transactions.
"""

import asyncio
from datetime import timedelta

import pandas as pd
import structlog
from fastapi import APIRouter, Depends, Request

from src.core.utils.date_utils import utcnow

from ...database.mongodb import MongoDB
from ...services.market_data.yfinance_bars import get_bars
from ..dependencies.auth import get_mongodb
from ..dependencies.rate_limit import limiter
from ..schemas.portfolio_models import (
    AnalysisMarker,
    OrderMarker,
    PortfolioHistoryDataPoint,
    PortfolioHistoryResponse,
)

logger = structlog.get_logger()

router = APIRouter()


# period → (yfinance granularity, lookback for order-marker filter)
_PERIOD_TO_GRANULARITY: dict[str, tuple[str, timedelta]] = {
    "1D": ("5min", timedelta(days=2)),
    "1M": ("daily", timedelta(days=35)),
    "1Y": ("daily", timedelta(days=370)),
    "All": ("weekly", timedelta(days=365 * 5)),
}


async def _build_value_series(
    holdings: list[tuple[str, float]], period: str
) -> list[PortfolioHistoryDataPoint]:
    """Σ qty * close per timestamp using whatever bars yfinance returns. Symbols
    that fail to fetch are skipped (logged) so one bad ticker doesn't kill the
    whole chart."""
    if not holdings:
        return []
    granularity, _ = _PERIOD_TO_GRANULARITY.get(period, _PERIOD_TO_GRANULARITY["1D"])
    outputsize = "compact" if period == "1D" else "full"

    sem = asyncio.Semaphore(8)

    async def _fetch_one(sym: str, qty: float) -> pd.Series | None:
        async with sem:
            try:
                df = await get_bars(sym, granularity, outputsize=outputsize)
                if df is None or df.empty or "Close" not in df.columns:
                    return None
                # `Close` Series indexed by datetime; multiply by qty
                return df["Close"].astype(float) * float(qty)
            except Exception as e:
                logger.warning(
                    "history_bar_fetch_failed",
                    symbol=sym,
                    granularity=granularity,
                    error=str(e),
                )
                return None

    series = await asyncio.gather(
        *(_fetch_one(sym, qty) for sym, qty in holdings)
    )
    valid = [s for s in series if s is not None]
    if not valid:
        return []

    # Outer-join all per-symbol series on their timestamp index, fill missing
    # bars (e.g. when one symbol has a halt) with the previous valid sample so
    # the sum doesn't dip when one ticker is briefly absent.
    df = pd.concat(valid, axis=1).sort_index().ffill().dropna(how="all")
    totals = df.sum(axis=1)

    out: list[PortfolioHistoryDataPoint] = []
    for ts, val in totals.items():
        # yfinance index is tz-aware (US/Eastern for intraday, naive for daily)
        if ts.tz is None:
            ts = ts.tz_localize("UTC")
        out.append(
            PortfolioHistoryDataPoint(timestamp=ts.to_pydatetime(), value=float(val))
        )
    return out


@router.get("/history", response_model=PortfolioHistoryResponse)
@limiter.limit("30/minute")
async def get_portfolio_history(
    request: Request,
    period: str = "1D",
    symbol: str | None = None,
    mongodb: MongoDB = Depends(get_mongodb),
) -> PortfolioHistoryResponse:
    """Reconstruct portfolio value series from current holdings × historical bars.

    Order markers come from the portfolio_orders collection (last 30 days)
    regardless of `period`, so filled trades are visible on every view.
    """
    end_time = utcnow()

    # Pull current holdings → list[(symbol, quantity)]
    holdings_collection = mongodb.get_collection("holdings")
    holdings_cursor = holdings_collection.find(
        {}, {"symbol": 1, "quantity": 1, "_id": 0}
    )
    holdings_pairs: list[tuple[str, float]] = []
    async for h in holdings_cursor:
        sym = h.get("symbol")
        qty = h.get("quantity")
        if sym and qty:
            holdings_pairs.append((str(sym).upper(), float(qty)))
    if symbol:
        wanted = symbol.upper()
        holdings_pairs = [p for p in holdings_pairs if p[0] == wanted]

    data_points = await _build_value_series(holdings_pairs, period)
    current_value = data_points[-1].value if data_points else 0.0

    # Order markers — keep the existing 30-day window for the chart annotations
    start_time = end_time - timedelta(days=30)
    orders_collection = mongodb.get_collection("portfolio_orders")
    order_query: dict = {
        "created_at": {"$gte": start_time, "$lte": end_time},
    }
    if symbol:
        order_query["symbol"] = symbol

    cursor = orders_collection.find(order_query).sort("created_at", -1).limit(100)
    order_markers: list[OrderMarker] = []
    async for order_dict in cursor:
        order_markers.append(
            OrderMarker(
                timestamp=order_dict["created_at"],
                symbol=order_dict["symbol"],
                side=order_dict["side"],
                quantity=order_dict["quantity"],
                status=order_dict["status"],
                filled_avg_price=order_dict.get("filled_avg_price"),
                order_id=order_dict["order_id"],
            )
        )

    markers: list[AnalysisMarker] = []

    logger.info(
        "Portfolio history reconstructed",
        period=period,
        holdings=len(holdings_pairs),
        data_points=len(data_points),
        order_markers=len(order_markers),
        current_value=round(current_value, 2),
    )

    return PortfolioHistoryResponse(
        data_points=data_points,
        markers=markers,
        order_markers=order_markers,
        current_value=current_value,
        period=period,
    )
