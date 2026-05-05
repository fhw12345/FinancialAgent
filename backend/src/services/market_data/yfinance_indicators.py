"""
Local technical indicator computation via pandas-ta-classic on yfinance bars.

Primary path for `get_trend_indicator` / `get_momentum_indicator` /
`get_volume_indicator`. AV's TECHNICAL_INDICATOR endpoint is fallback only —
keeping AV as primary burns the 25/day free-tier quota in a few page loads.

Output DataFrame shape mirrors what `formatters.technical.format_technical_indicator`
expects (column names are checked there for MACD; single-col indicators just
display whatever name we set as `Current {function}: X`).
"""

from __future__ import annotations

import asyncio

import pandas as pd
import pandas_ta_classic as ta
import structlog

from . import yfinance_bars

logger = structlog.get_logger()


SUPPORTED_FUNCTIONS = {
    "SMA",
    "EMA",
    "VWAP",
    "RSI",
    "MACD",
    "STOCH",
    "AD",
    "OBV",
    "ADX",
    "AROON",
    "BBANDS",
}


def _compute_sync(
    df: pd.DataFrame,
    function: str,
    time_period: int | None,
) -> pd.DataFrame:
    """Run the pandas-ta-classic call and rename cols to match the formatter
    contract (especially MACD_Signal / Real Upper Band / etc., which are
    string-matched downstream)."""
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"] if "Volume" in df.columns else None

    if function == "SMA":
        out = ta.sma(close, length=time_period or 20).to_frame(name="SMA")
    elif function == "EMA":
        out = ta.ema(close, length=time_period or 20).to_frame(name="EMA")
    elif function == "VWAP":
        if volume is None:
            raise ValueError("VWAP requires Volume column")
        out = ta.vwap(high=high, low=low, close=close, volume=volume).to_frame(
            name="VWAP"
        )
    elif function == "RSI":
        out = ta.rsi(close, length=time_period or 14).to_frame(name="RSI")
    elif function == "MACD":
        raw = ta.macd(close, fast=12, slow=26, signal=9)
        # pandas-ta-classic emits MACD_12_26_9 / MACDh_12_26_9 / MACDs_12_26_9
        out = pd.DataFrame(
            {
                "MACD": raw["MACD_12_26_9"],
                "MACD_Hist": raw["MACDh_12_26_9"],
                "MACD_Signal": raw["MACDs_12_26_9"],
            }
        )
    elif function == "STOCH":
        raw = ta.stoch(high=high, low=low, close=close, k=5, d=3, smooth_k=3)
        # pandas-ta-classic emits STOCHk_5_3_3 / STOCHd_5_3_3
        out = pd.DataFrame(
            {
                "SlowK": raw[raw.columns[0]],
                "SlowD": raw[raw.columns[1]],
            }
        )
    elif function == "AD":
        out = ta.ad(high=high, low=low, close=close, volume=volume).to_frame(
            name="Chaikin A/D"
        )
    elif function == "OBV":
        if volume is None:
            raise ValueError("OBV requires Volume column")
        out = ta.obv(close=close, volume=volume).to_frame(name="OBV")
    elif function == "ADX":
        raw = ta.adx(high=high, low=low, close=close, length=time_period or 14)
        # pandas-ta-classic emits ADX_14 / DMP_14 / DMN_14 — keep ADX only,
        # which matches AV's ADX response (ADX series only).
        adx_col = next((c for c in raw.columns if c.startswith("ADX")), None)
        if adx_col is None:
            raise ValueError("ADX column not produced by pandas-ta-classic")
        out = raw[[adx_col]].rename(columns={adx_col: "ADX"})
    elif function == "AROON":
        raw = ta.aroon(high=high, low=low, length=time_period or 14)
        # pandas-ta-classic emits AROOND_14 / AROONU_14 / AROONOSC_14
        up = next((c for c in raw.columns if c.startswith("AROONU")), None)
        down = next((c for c in raw.columns if c.startswith("AROOND")), None)
        if up is None or down is None:
            raise ValueError("AROON columns not produced by pandas-ta-classic")
        out = pd.DataFrame({"Aroon Up": raw[up], "Aroon Down": raw[down]})
    elif function == "BBANDS":
        raw = ta.bbands(close, length=time_period or 20, std=2)
        # pandas-ta-classic emits BBL_/BBM_/BBU_/BBB_/BBP_ — keep upper/mid/lower
        upper = next((c for c in raw.columns if c.startswith("BBU")), None)
        mid = next((c for c in raw.columns if c.startswith("BBM")), None)
        lower = next((c for c in raw.columns if c.startswith("BBL")), None)
        if upper is None or mid is None or lower is None:
            raise ValueError("BBANDS columns not produced by pandas-ta-classic")
        out = pd.DataFrame(
            {
                "Real Upper Band": raw[upper],
                "Real Middle Band": raw[mid],
                "Real Lower Band": raw[lower],
            }
        )
    else:
        raise ValueError(f"Unsupported function: {function}")

    return out.dropna(how="all")


async def compute_indicator(
    symbol: str,
    function: str,
    interval: str = "daily",
    time_period: int | None = None,
) -> pd.DataFrame:
    """
    Compute a technical indicator locally from yfinance bars.

    Args:
        symbol: Ticker (e.g. "AAPL")
        function: Indicator name (SMA, EMA, RSI, MACD, STOCH, BBANDS, AD, OBV,
            ADX, AROON, VWAP)
        interval: yfinance-bars granularity (daily, weekly, monthly, 1min,
            5min, 15min, 30min, 60min)
        time_period: Lookback for indicators that take one (RSI 14, BBANDS 20,
            ADX 14, etc.). None → indicator's natural default.

    Returns:
        DataFrame indexed by datetime with indicator columns named to match
        what `format_technical_indicator(...)` expects.

    Raises:
        ValueError: function not supported, or pandas-ta produced unexpected
            column names.
        Anything `yfinance_bars.get_bars` raises — typically RuntimeError on
        empty data or rate-limit.
    """
    fn = function.upper()
    if fn not in SUPPORTED_FUNCTIONS:
        raise ValueError(f"Unsupported indicator function: {function}")

    bars = await yfinance_bars.get_bars(symbol, interval, outputsize="full")
    if bars.empty:
        raise RuntimeError(f"yfinance returned no bars for {symbol} ({interval})")

    return await asyncio.to_thread(_compute_sync, bars, fn, time_period)
