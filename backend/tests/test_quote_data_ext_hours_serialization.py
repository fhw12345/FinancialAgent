"""W3.18 — round-trip serialization for QuoteData's extended-hours fields.

The four ext-hours fields (price, session, change_percent, asof) must
survive a `to_dict` → JSON-style transit → `from_dict` cycle so the redis
cache layer and the API response don't silently drop them. We also pin
backwards compatibility: a dict written before W3.18 (no ext_hours_*
keys) still deserialises cleanly with all four fields = None.
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.services.data_manager.types import QuoteData


def _base_kwargs() -> dict:
    return {
        "symbol": "NVDA",
        "price": 215.20,
        "volume": 50_000_000,
        "latest_trading_day": "2026-05-08",
        "previous_close": 213.10,
        "change": 2.10,
        "change_percent": 0.985,
        "open": 213.50,
        "high": 216.00,
        "low": 213.00,
        "session": "closed",
        "source": "yfinance",
        "asof": datetime(2026, 5, 8, 21, 0, tzinfo=UTC),
    }


def test_ext_hours_fields_round_trip_through_dict() -> None:
    asof = datetime(2026, 5, 8, 21, 0, tzinfo=UTC)
    ext_asof = datetime(2026, 5, 8, 23, 55, tzinfo=UTC)
    q = QuoteData(
        **_base_kwargs(),
        ext_hours_price=215.05,
        ext_hours_session="post",
        ext_hours_change_percent=-0.07,
        ext_hours_asof=ext_asof,
    )
    # Sanity: explicit asof so the test does not depend on construction order.
    assert q.asof == asof

    d = q.to_dict()
    assert d["ext_hours_price"] == 215.05
    assert d["ext_hours_session"] == "post"
    assert d["ext_hours_change_percent"] == -0.07
    assert d["ext_hours_asof"] == ext_asof.isoformat()

    restored = QuoteData.from_dict(d)
    assert restored.ext_hours_price == 215.05
    assert restored.ext_hours_session == "post"
    assert restored.ext_hours_change_percent == -0.07
    assert restored.ext_hours_asof == ext_asof


def test_legacy_dict_without_ext_hours_keys_deserialises() -> None:
    """A redis row written before W3.18 has no ext_hours_* keys. The
    dataclass must still parse it with all four ext fields = None."""
    legacy = {
        "symbol": "AAPL",
        "price": 187.10,
        "volume": 40_000_000,
        "latest_trading_day": "2026-05-07",
        "previous_close": 186.40,
        "change": 0.70,
        "change_percent": 0.376,
        "open": 186.50,
        "high": 188.00,
        "low": 186.10,
        "session": "regular",
        "source": "finnhub",
        "asof": "2026-05-07T20:00:00+00:00",
    }
    q = QuoteData.from_dict(legacy)
    assert q.ext_hours_price is None
    assert q.ext_hours_session is None
    assert q.ext_hours_change_percent is None
    assert q.ext_hours_asof is None


def test_ext_hours_defaults_none_when_omitted() -> None:
    """Constructing QuoteData without specifying ext-hours kwargs leaves
    all four fields at None — needed so existing call sites in the
    fetcher / API layer don't have to pass explicit None when no
    companion price is available."""
    q = QuoteData(**_base_kwargs())
    assert q.ext_hours_price is None
    assert q.ext_hours_session is None
    assert q.ext_hours_change_percent is None
    assert q.ext_hours_asof is None
    # to_dict still emits the keys (with null values) so consumers can
    # rely on the schema shape.
    d = q.to_dict()
    assert d["ext_hours_price"] is None
    assert d["ext_hours_session"] is None
    assert d["ext_hours_change_percent"] is None
    assert d["ext_hours_asof"] is None


def test_ext_hours_asof_accepts_datetime_object_in_dict() -> None:
    """When constructing from an in-memory dict (not JSON), asof may
    already be a datetime instance. Mirror the existing `asof` parsing
    behaviour."""
    ext_asof = datetime(2026, 5, 8, 13, 25, tzinfo=UTC)
    d = {
        **{k: v for k, v in _base_kwargs().items() if k != "asof"},
        "asof": datetime(2026, 5, 8, 13, 0, tzinfo=UTC),
        "ext_hours_price": 214.80,
        "ext_hours_session": "pre",
        "ext_hours_change_percent": -0.19,
        "ext_hours_asof": ext_asof,
    }
    q = QuoteData.from_dict(d)
    assert q.ext_hours_asof == ext_asof
    assert q.ext_hours_session == "pre"
