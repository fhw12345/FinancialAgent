"""W3.18 — integration tests for the DataManager ext-hours enrichment
path: `_enrich_extended_hours_companion` + `_fetch_yfinance_info`.

Tests cover:
  * Primary session=regular/closed → companion populated when fresh
    info is available.
  * Primary session=pre/post → enrichment is a no-op (primary IS the
    ext-hours print).
  * yfinance info fetch failure does NOT break the primary quote.
  * Cache hit on the dedicated `market:quote_ext:<SYM>` key avoids a
    second yfinance roundtrip.
  * Empty/None info dicts (legacy / disabled providers) leave fields
    None without crashing.

We mock both the cache layer and yfinance at module level. The W3.18
PRD's principle: ext-hours is decoration; failures must be silent.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.data_manager.manager import DataManager
from src.services.data_manager.types import QuoteData


def _make_quote(session: str = "closed", price: float = 215.20) -> QuoteData:
    return QuoteData(
        symbol="NVDA",
        price=price,
        volume=10_000_000,
        latest_trading_day="2026-05-08",
        previous_close=213.10,
        change=2.10,
        change_percent=0.985,
        open=213.50,
        high=216.00,
        low=213.00,
        session=session,  # type: ignore[arg-type]
        source="finnhub",
        asof=datetime(2026, 5, 8, 21, 0, tzinfo=UTC),
    )


def _make_dm() -> DataManager:
    """Build a DataManager with mock dependencies. Cache mock supports
    both `get_with_fetch` (used by `_enrich_extended_hours_companion`)
    and `get`/`set`."""
    cache = MagicMock()
    cache.get_with_fetch = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()

    redis = MagicMock()
    av_service = MagicMock()
    finnhub_service = MagicMock()

    dm = DataManager(
        redis_cache=redis,
        alpha_vantage_service=av_service,
        finnhub_service=finnhub_service,
    )
    # Replace the CacheOperations wrapper with our mock so we can
    # assert calls directly.
    dm._cache = cache  # type: ignore[assignment]
    return dm


@pytest.mark.asyncio
async def test_enrich_populates_ext_fields_when_companion_fresh() -> None:
    dm = _make_dm()
    quote = _make_quote(session="closed")

    fresh_info = {
        "postMarketPrice": 215.05,
        "postMarketTime": int(
            (datetime.now(UTC) - timedelta(hours=2)).timestamp()
        ),
        "preMarketPrice": None,
        "preMarketTime": None,
    }
    dm._cache.get_with_fetch = AsyncMock(return_value=fresh_info)  # type: ignore[attr-defined]

    await dm._enrich_extended_hours_companion(quote)

    assert quote.ext_hours_price == pytest.approx(215.05)
    assert quote.ext_hours_session == "post"
    expected_pct = (215.05 - 215.20) / 215.20 * 100.0
    assert quote.ext_hours_change_percent == pytest.approx(expected_pct)
    assert quote.ext_hours_asof is not None


@pytest.mark.asyncio
async def test_enrich_no_op_when_primary_session_is_post() -> None:
    """Primary IS the after-hours print — companion is redundant."""
    dm = _make_dm()
    quote = _make_quote(session="post")
    dm._cache.get_with_fetch = AsyncMock()  # type: ignore[attr-defined]

    await dm._enrich_extended_hours_companion(quote)

    # No cache lookup, no field population.
    assert dm._cache.get_with_fetch.await_count == 0  # type: ignore[attr-defined]
    assert quote.ext_hours_price is None


@pytest.mark.asyncio
async def test_enrich_no_op_when_primary_session_is_pre() -> None:
    dm = _make_dm()
    quote = _make_quote(session="pre")
    dm._cache.get_with_fetch = AsyncMock()  # type: ignore[attr-defined]

    await dm._enrich_extended_hours_companion(quote)

    assert dm._cache.get_with_fetch.await_count == 0  # type: ignore[attr-defined]
    assert quote.ext_hours_price is None


@pytest.mark.asyncio
async def test_enrich_silent_when_info_dict_empty() -> None:
    """Cache hit with empty dict (e.g. yfinance returned None and we
    cached the negative result) leaves fields None — no exception."""
    dm = _make_dm()
    quote = _make_quote(session="closed")
    dm._cache.get_with_fetch = AsyncMock(return_value={})  # type: ignore[attr-defined]

    await dm._enrich_extended_hours_companion(quote)

    assert quote.ext_hours_price is None
    assert quote.ext_hours_session is None


@pytest.mark.asyncio
async def test_enrich_silent_when_info_stale() -> None:
    """A 25h-old post-market timestamp is past the 18h gate — companion
    rejected, no fields written."""
    dm = _make_dm()
    quote = _make_quote(session="closed")
    stale_info = {
        "postMarketPrice": 215.05,
        "postMarketTime": int(
            (datetime.now(UTC) - timedelta(hours=25)).timestamp()
        ),
    }
    dm._cache.get_with_fetch = AsyncMock(return_value=stale_info)  # type: ignore[attr-defined]

    await dm._enrich_extended_hours_companion(quote)

    assert quote.ext_hours_price is None


@pytest.mark.asyncio
async def test_enrich_uses_dedicated_cache_key() -> None:
    """Pin the W3.18 cache key contract: enrichment hits
    market:quote_ext:NVDA, NOT market:quote:NVDA."""
    dm = _make_dm()
    quote = _make_quote(session="closed")
    dm._cache.get_with_fetch = AsyncMock(return_value={})  # type: ignore[attr-defined]

    await dm._enrich_extended_hours_companion(quote)

    call_args = dm._cache.get_with_fetch.await_args  # type: ignore[attr-defined]
    cache_key = call_args.args[0] if call_args.args else call_args.kwargs.get("key")
    assert cache_key == "market:quote_ext:NVDA"


@pytest.mark.asyncio
async def test_get_quote_swallows_enrichment_exceptions() -> None:
    """Even if `_enrich_extended_hours_companion` raises, get_quote
    must still return the primary quote — ext-hours is decoration."""
    dm = _make_dm()
    primary_dict = _make_quote(session="closed").to_dict()
    dm._cache.get_with_fetch = AsyncMock(return_value=primary_dict)  # type: ignore[attr-defined]

    with patch.object(
        dm,
        "_enrich_extended_hours_companion",
        side_effect=RuntimeError("network blew up"),
    ):
        q = await dm.get_quote("NVDA")

    assert q.symbol == "NVDA"
    assert q.price == pytest.approx(215.20)
    assert q.ext_hours_price is None  # never enriched


@pytest.mark.asyncio
async def test_fetch_yfinance_info_returns_subset_of_keys() -> None:
    """The fetcher must return exactly the W3.18 key subset, not the
    full ~150-key info blob (saves redis space + matches the cache
    contract the helper expects)."""
    fake_info = {
        "preMarketPrice": 214.80,
        "preMarketTime": 1746780000,
        "postMarketPrice": 215.05,
        "postMarketTime": 1746790000,
        "marketState": "POST",
        "regularMarketPrice": 215.20,
        "hasPrePostMarketData": True,
        # Extra noise that should NOT be in the result:
        "longName": "NVIDIA Corp",
        "marketCap": 2_500_000_000_000,
    }
    ticker = SimpleNamespace(info=fake_info)
    with patch("yfinance.Ticker", return_value=ticker):
        result = await DataManager._fetch_yfinance_info("NVDA")

    assert result is not None
    assert "longName" not in result
    assert "marketCap" not in result
    assert result["preMarketPrice"] == 214.80
    assert result["postMarketTime"] == 1746790000
    assert result["marketState"] == "POST"


@pytest.mark.asyncio
async def test_fetch_yfinance_info_returns_none_on_exception() -> None:
    """yfinance.info routinely raises (rate-limit, network, malformed
    response). The fetcher must convert to None so the cache layer
    treats it as 'don't cache' rather than caching a corrupt blob."""
    with patch(
        "yfinance.Ticker", side_effect=RuntimeError("rate limit")
    ):
        result = await DataManager._fetch_yfinance_info("NVDA")

    assert result is None
