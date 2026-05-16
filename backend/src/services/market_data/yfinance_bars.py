"""
OHLCV bars via yfinance — primary source for chart data.

Replaces Alpha Vantage TIME_SERIES_INTRADAY / DAILY / WEEKLY / MONTHLY for
chart/analysis surfaces. yfinance has no key, no daily cap, and the same OHLCV
fields. Output is a pandas DataFrame in the same shape AV's wrappers return,
so the caller's `_dataframe_to_ohlcv()` logic is unchanged.

Granularity → yfinance interval/period mapping:

  Granularity      yf.interval   yf.period (default)
  ─────────────    ───────────   ───────────────────
  1min             1m            7d   (Yahoo caps 1m at 7d)
  5min             5m            60d  (caps at 60d)
  15min            15m           60d
  30min            30m           60d
  60min            60m           730d
  daily            1d            2y or max
  weekly           1wk           max
  monthly          1mo           max

`outputsize` ("compact"|"full") is mapped to a sensible period:
- compact → ~100 most recent bars
- full → max available (limited by Yahoo's per-interval cap)
"""

from __future__ import annotations

import asyncio

import pandas as pd
import structlog
import yfinance as yf

logger = structlog.get_logger()


# Granularity string → yfinance (interval, period_compact, period_full)
_INTERVAL_MAP: dict[str, tuple[str, str, str]] = {
    "1min": ("1m", "1d", "7d"),
    "5min": ("5m", "5d", "60d"),
    "15min": ("15m", "5d", "60d"),
    "30min": ("30m", "10d", "60d"),
    "60min": ("60m", "60d", "730d"),
    "daily": ("1d", "3mo", "max"),
    "weekly": ("1wk", "1y", "max"),
    "monthly": ("1mo", "5y", "max"),
}


def _fetch_sync(
    symbol: str, granularity: str, outputsize: str, prepost: bool = False
) -> pd.DataFrame:
    """Blocking yfinance call. Returns AV-shaped DataFrame indexed by datetime.

    When prepost=True, includes pre-market (4:00-9:30 ET) and post-market
    (16:00-20:00 ET) extended-hours bars in addition to RTH.
    """
    spec = _INTERVAL_MAP.get(granularity)
    if spec is None:
        raise ValueError(f"Unsupported granularity for yfinance bars: {granularity}")
    interval, period_compact, period_full = spec
    period = period_full if outputsize == "full" else period_compact

    ticker = yf.Ticker(symbol)
    df = ticker.history(
        period=period, interval=interval, auto_adjust=False, prepost=prepost
    )
    if df is None or df.empty:
        raise RuntimeError(f"yfinance returned no bars for {symbol} ({granularity})")

    # yfinance columns are already 'Open', 'High', 'Low', 'Close', 'Volume' —
    # the same shape AV's wrappers return, so _dataframe_to_ohlcv() works
    # without changes. Drop any extras (Dividends, Stock Splits) to keep
    # downstream conversion lean.
    keep = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]
    df = df[keep].copy()
    return df


async def get_bars(
    symbol: str,
    granularity: str,
    outputsize: str = "compact",
    prepost: bool = False,
) -> pd.DataFrame:
    """Async wrapper. Raises if yfinance can't return data so the caller's
    fallback chain (→ AV) can take over.

    prepost=True includes extended-hours bars (pre 4:00-9:30 ET, post
    16:00-20:00 ET). Default False keeps chart/indicator surfaces RTH-only.
    """
    return await asyncio.to_thread(
        _fetch_sync, symbol, granularity, outputsize, prepost
    )
