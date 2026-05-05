"""Sanity & format-parity tests for the new yfinance data adapters.

These tests hit the **live** yfinance public endpoints, so they're marked
with `@pytest.mark.integration` and skipped by default. Run them with:

    pytest -m integration tests/test_yfinance_adapters_parity.py

What they verify (the things most likely to silently break and ship a bad
chart / wrong quote to the UI):

1. **Quote shape** — yfinance fallback in DataManager returns a QuoteData
   with all required fields populated, ticker echoed back uppercase, price
   sane (> 0), and change_percent parses as a float.
2. **OHLCV bars shape** — `yfinance_bars.get_bars()` returns a DataFrame
   with the same column names AV's wrappers produce (Open/High/Low/Close/
   Volume), so DataManager._dataframe_to_ohlcv() works without changes.
3. **Bar ordering & continuity** — bars indexed by ascending datetime, no
   duplicate indices, prices are positive.
4. **Movers shape** — yfinance_movers returns the AV-shape dict with three
   non-empty buckets and rows containing `ticker, price, change_amount,
   change_percentage, volume`.
5. **Symbol search shape** — yfinance_search returns rows with the keys
   the SymbolSearchResult model expects.

We deliberately don't compare yfinance prices against AV prices: the AV
free-tier key is exhausted, AV bars and yfinance bars use different last-
price snapshots, and either can be 1-2% off the other on a volatile day —
that's noise, not a bug.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_yfinance_bars_shape() -> None:
    from src.services.market_data.yfinance_bars import get_bars

    df = await get_bars("AAPL", "daily", "compact")
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    # Same columns AV's wrappers produce — _dataframe_to_ohlcv expects these
    for col in ("Open", "High", "Low", "Close", "Volume"):
        assert col in df.columns, f"missing column {col} in yfinance daily bars"
    # Sanity: prices positive, ordered ascending, no duplicates
    assert (df["Close"] > 0).all()
    assert df.index.is_monotonic_increasing
    assert df.index.is_unique


@pytest.mark.asyncio
async def test_yfinance_bars_intraday() -> None:
    from src.services.market_data.yfinance_bars import get_bars

    df = await get_bars("AAPL", "1min", "compact")
    assert not df.empty
    assert (df["Close"] > 0).all()


@pytest.mark.asyncio
async def test_datamanager_yfinance_quote_fallback() -> None:
    """Bypass Finnhub by going straight at the yfinance fallback method.
    Verifies the QuoteData shape downstream code expects."""
    from src.services.data_manager.manager import DataManager

    qd = await DataManager._fetch_quote_yfinance("AAPL")
    assert qd.symbol == "AAPL"
    assert qd.price > 0
    assert qd.previous_close > 0
    # change_percent is a float on QuoteData; downstream str-cast should work
    assert isinstance(qd.change_percent, float)
    assert qd.high >= qd.low
    # latest_trading_day is parseable
    if qd.latest_trading_day:
        # Either ISO date or datetime — just verify it doesn't crash
        try:
            datetime.fromisoformat(str(qd.latest_trading_day).split(" ")[0])
        except ValueError:
            pytest.fail(f"unparseable latest_trading_day: {qd.latest_trading_day!r}")


@pytest.mark.asyncio
async def test_yfinance_movers_shape() -> None:
    from src.services.market_data.yfinance_movers import get_market_movers

    data = await get_market_movers(count=10)
    for bucket in ("top_gainers", "top_losers", "most_actively_traded"):
        rows = data.get(bucket, [])
        assert rows, f"yfinance returned empty {bucket}"
        first = rows[0]
        for k in ("ticker", "price", "change_amount", "change_percentage", "volume"):
            assert k in first, f"missing {k} in {bucket} row: {first}"
        # change_percentage matches AV's "57.2513%" string contract
        assert first["change_percentage"].endswith("%")
    assert data.get("source") == "yfinance"


@pytest.mark.asyncio
async def test_yfinance_search_returns_shape() -> None:
    from src.services.market_data.yfinance_search import search_symbols

    results = await search_symbols("CRWV", limit=3)
    assert results, "yfinance search returned no results for CRWV"
    first = results[0]
    for k in ("symbol", "name", "exchange", "type", "match_type", "confidence"):
        assert k in first, f"missing {k} in search result: {first}"
    assert first["symbol"] == "CRWV"
    assert 0.0 <= first["confidence"] <= 1.0
