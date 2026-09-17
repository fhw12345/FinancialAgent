"""Bounded outer market adapter: unadjusted closing marks and adjusted-close returns."""

import asyncio
import math
from datetime import date, timedelta
from typing import Any

import pandas as pd
import yfinance as yf

from ...models.portfolio_risk import RiskAsset, SessionReturn
from .calendar import sessions


def _fetch(symbol: str, session: date) -> RiskAsset:
    ticker = yf.Ticker(symbol)
    history = ticker.history(
        start=(session - timedelta(days=200)).isoformat(),
        end=(session + timedelta(days=1)).isoformat(),
        interval="1d",
        auto_adjust=False,
        actions=True,
        timeout=10,
    )
    info: dict[str, Any] = ticker.info or {}
    if info.get("quoteType") not in ("EQUITY", "ETF"):
        return RiskAsset(symbol=symbol, errors=["INSTRUMENT_UNSUPPORTED_OR_UNKNOWN"])
    asset = RiskAsset(
        symbol=symbol,
        currency=info.get("currency"),
        sector=info.get("sector") or "Unknown",
        beta=info.get("beta"),
    )
    if (
        history is None
        or history.empty
        or "Close" not in history
        or "Adj Close" not in history
    ):
        return asset.model_copy(update={"errors": ["ADJUSTED_HISTORY_UNAVAILABLE"]})
    dates = [pd.Timestamp(d).date() for d in history.index]
    if len(set(dates)) != len(dates) or any(d > session for d in dates):
        return asset.model_copy(update={"errors": ["INVALID_PROVIDER_SESSIONS"]})
    allowed = set(sessions(session, 160))
    if any(d not in allowed for d in dates):
        return asset.model_copy(update={"errors": ["NON_SESSION_PROVIDER_DATA"]})
    if session in dates:
        asset.mark = float(history.iloc[dates.index(session)]["Close"])
        asset.mark_session = session
    # A missing intermediate session must not become a one-day return spanning two days.
    previous = {
        d: p
        for p, d in zip(
            sessions(session, 161)[:-1], sessions(session, 161)[1:], strict=True
        )
    }
    adjusted = {
        d: float(value) for d, value in zip(dates, history["Adj Close"], strict=True)
    }
    if any(not math.isfinite(v) or v <= 0 for v in adjusted.values()):
        return asset.model_copy(update={"errors": ["INVALID_ADJUSTED_PRICE"]})
    points = []
    for d in sorted(adjusted):
        p = previous.get(d)
        if p in adjusted and adjusted[p] > 0:
            points.append(
                SessionReturn(
                    session_date=d, total_return=adjusted[d] / adjusted[p] - 1
                )
            )
    asset.returns = points[-60:]
    # Revalidate constructed values, including provider NaN/Infinity/zero marks.
    return RiskAsset.model_validate(asset.model_dump())


async def fetch_asset(symbol: str, session: date) -> RiskAsset:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_fetch, symbol, session), timeout=15
        )
    except Exception:
        return RiskAsset(symbol=symbol, errors=["PROVIDER_UNAVAILABLE_OR_INVALID"])
