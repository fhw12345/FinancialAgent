"""Unit tests for extended-hours price selection.

Covers _extended_hours_price helper plus the two quote paths that wrap it:
- DataManager._fetch_quote_yfinance (manager.py)
- _yf_quote_sync (services/market_data/quotes.py)
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.services.data_manager.manager import DataManager, _extended_hours_price


def _make_hist(rows: list[tuple[str, float, int]]) -> pd.DataFrame:
    """Build a yfinance-style 1m bar DataFrame.

    rows: list of (iso_ts, close, volume).
    """
    if not rows:
        idx = pd.DatetimeIndex([], tz="America/New_York")
        return pd.DataFrame(
            {"Open": [], "High": [], "Low": [], "Close": [], "Volume": []},
            index=idx,
        )
    ts = pd.DatetimeIndex([r[0] for r in rows]).tz_localize("America/New_York")
    closes = [r[1] for r in rows]
    vols = [r[2] for r in rows]
    return pd.DataFrame(
        {
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Close": closes,
            "Volume": vols,
        },
        index=ts,
    )


# ===== _extended_hours_price helper =====


class TestExtendedHoursPriceHelper:
    def test_pre_session_uses_last_bar_close(self) -> None:
        hist = _make_hist(
            [
                ("2026-05-07 08:00", 287.10, 1500),
                ("2026-05-07 09:28", 289.35, 2200),
            ]
        )
        assert _extended_hours_price(hist, "pre", fallback=287.51) == pytest.approx(
            289.35
        )

    def test_post_session_uses_last_bar_close(self) -> None:
        hist = _make_hist(
            [
                ("2026-05-07 16:30", 290.10, 800),
                ("2026-05-07 18:00", 291.20, 1200),
            ]
        )
        assert _extended_hours_price(hist, "post", fallback=290.00) == pytest.approx(
            291.20
        )

    def test_regular_session_returns_fallback(self) -> None:
        hist = _make_hist([("2026-05-07 12:00", 295.00, 5000)])
        assert _extended_hours_price(hist, "regular", fallback=287.51) == 287.51

    def test_closed_session_returns_fallback(self) -> None:
        hist = _make_hist([("2026-05-07 04:00", 286.00, 100)])
        assert _extended_hours_price(hist, "closed", fallback=287.51) == 287.51

    def test_none_hist_returns_fallback(self) -> None:
        assert _extended_hours_price(None, "pre", fallback=287.51) == 287.51

    def test_empty_hist_returns_fallback(self) -> None:
        assert _extended_hours_price(_make_hist([]), "pre", fallback=287.51) == 287.51

    def test_all_zero_volume_hist_returns_fallback(self) -> None:
        # No previous_close hint provided → cannot tell if zero-vol bars are
        # real prepost prints or stale; safest to fall back.
        hist = _make_hist(
            [
                ("2026-05-07 08:00", 287.10, 0),
                ("2026-05-07 09:28", 289.35, 0),
            ]
        )
        assert _extended_hours_price(hist, "pre", fallback=287.51) == 287.51

    def test_zero_volume_priced_bars_used_when_prev_close_differs(self) -> None:
        # yfinance frequently reports pre-market with Volume=0 but real Close
        # prices. When previous_close is provided and the bars deviate from
        # it, treat them as legitimate prepost prints.
        hist = _make_hist(
            [
                ("2026-05-07 08:00", 287.10, 0),
                ("2026-05-07 09:28", 289.35, 0),
            ]
        )
        assert _extended_hours_price(
            hist, "pre", fallback=287.51, previous_close=287.94
        ) == pytest.approx(289.35)

    def test_zero_volume_bars_at_prev_close_return_fallback(self) -> None:
        # Stale zero-volume bars whose Close equals previous_close carry no
        # signal; fall back to the regular-session price.
        hist = _make_hist(
            [
                ("2026-05-07 08:00", 287.94, 0),
                ("2026-05-07 09:28", 287.94, 0),
            ]
        )
        assert (
            _extended_hours_price(hist, "pre", fallback=287.51, previous_close=287.94)
            == 287.51
        )

    def test_filters_zero_volume_trailing_bar(self) -> None:
        hist = _make_hist(
            [
                ("2026-05-07 08:00", 287.10, 1500),
                ("2026-05-07 09:28", 289.35, 2200),
                ("2026-05-07 09:29", 999.99, 0),  # phantom trailing bar
            ]
        )
        assert _extended_hours_price(hist, "pre", fallback=287.51) == pytest.approx(
            289.35
        )


# ===== DataManager._fetch_quote_yfinance =====


def _patch_yfinance(
    hist: pd.DataFrame, last_price: float, prev_close: float
) -> MagicMock:
    """Build a mock yf.Ticker that returns canned fast_info + history."""
    ticker = MagicMock()
    ticker.fast_info = SimpleNamespace(
        last_price=last_price,
        previous_close=prev_close,
        last_volume=1234,
        open=last_price,
        day_high=last_price,
        day_low=last_price,
    )
    ticker.history.return_value = hist
    return ticker


def _session_for(label: str) -> str:
    return label


@pytest.mark.asyncio
async def test_fetch_quote_yfinance_pre_uses_bar_close() -> None:
    hist = _make_hist(
        [
            ("2026-05-07 08:00", 287.10, 1500),
            ("2026-05-07 09:28", 289.35, 2200),
        ]
    )
    ticker = _patch_yfinance(hist, last_price=287.51, prev_close=287.40)
    with (
        patch("yfinance.Ticker", return_value=ticker),
        patch(
            "src.services.market_data.get_market_session",
            side_effect=lambda _ts: "pre",
        ),
    ):
        qd = await DataManager._fetch_quote_yfinance("AAPL")
    assert qd.session == "pre"
    assert qd.price == pytest.approx(289.35)
    assert qd.previous_close == pytest.approx(287.40)
    expected_pct = (289.35 - 287.40) / 287.40 * 100
    assert qd.change_percent == pytest.approx(expected_pct)


@pytest.mark.asyncio
async def test_fetch_quote_yfinance_regular_uses_fast_info() -> None:
    hist = _make_hist([("2026-05-07 12:00", 290.50, 5000)])
    ticker = _patch_yfinance(hist, last_price=290.50, prev_close=287.40)
    with (
        patch("yfinance.Ticker", return_value=ticker),
        patch(
            "src.services.market_data.get_market_session",
            side_effect=lambda _ts: "regular",
        ),
    ):
        qd = await DataManager._fetch_quote_yfinance("AAPL")
    assert qd.session == "regular"
    assert qd.price == pytest.approx(290.50)
    expected_pct = (290.50 - 287.40) / 287.40 * 100
    assert qd.change_percent == pytest.approx(expected_pct)


@pytest.mark.asyncio
async def test_fetch_quote_yfinance_post_uses_bar_close() -> None:
    hist = _make_hist(
        [
            ("2026-05-07 16:30", 291.10, 700),
            ("2026-05-07 18:00", 292.40, 950),
        ]
    )
    ticker = _patch_yfinance(hist, last_price=290.10, prev_close=287.40)
    with (
        patch("yfinance.Ticker", return_value=ticker),
        patch(
            "src.services.market_data.get_market_session",
            side_effect=lambda _ts: "post",
        ),
    ):
        qd = await DataManager._fetch_quote_yfinance("AAPL")
    assert qd.session == "post"
    assert qd.price == pytest.approx(292.40)


@pytest.mark.asyncio
async def test_fetch_quote_yfinance_closed_uses_fast_info() -> None:
    hist = _make_hist([("2026-05-04 02:00", 285.00, 100)])
    ticker = _patch_yfinance(hist, last_price=287.40, prev_close=287.40)
    with (
        patch("yfinance.Ticker", return_value=ticker),
        patch(
            "src.services.market_data.get_market_session",
            side_effect=lambda _ts: "closed",
        ),
    ):
        qd = await DataManager._fetch_quote_yfinance("AAPL")
    assert qd.session == "closed"
    assert qd.price == pytest.approx(287.40)


@pytest.mark.asyncio
async def test_fetch_quote_yfinance_history_exception_falls_back() -> None:
    """If yfinance.history() raises, session defaults to regular and price
    falls back to fast_info.last_price — endpoint must not crash."""
    ticker = MagicMock()
    ticker.fast_info = SimpleNamespace(
        last_price=287.51,
        previous_close=287.40,
        last_volume=0,
        open=0.0,
        day_high=0.0,
        day_low=0.0,
    )
    ticker.history.side_effect = RuntimeError("yfinance rate limit")
    with patch("yfinance.Ticker", return_value=ticker):
        qd = await DataManager._fetch_quote_yfinance("AAPL")
    assert qd.session == "regular"
    assert qd.price == pytest.approx(287.51)


# ===== quotes.py:_yf_quote_sync =====


class TestYfQuoteSync:
    @pytest.fixture
    def hist_pre(self) -> pd.DataFrame:
        # Two prepost bars from this morning. With prepost=True hist[-2] is
        # itself a pre-market bar (NOT yesterday's RTH close), so the code
        # under test must source previous_close from ticker.info instead.
        return _make_hist(
            [
                ("2026-05-07 08:00", 287.10, 1500),
                ("2026-05-07 09:28", 289.35, 2200),
            ]
        )

    def _run_with(
        self,
        hist: pd.DataFrame,
        session: str,
        info: dict | None = None,
    ) -> dict:
        from src.services.market_data import quotes as quotes_mod

        ticker = MagicMock()
        ticker.info = (
            info
            if info is not None
            else {
                "currentPrice": 287.51,
                "regularMarketPrice": 287.51,
                "previousClose": 287.40,
            }
        )
        ticker.history.return_value = hist
        with (
            patch.object(quotes_mod.yf, "Ticker", return_value=ticker),
            patch(
                "src.services.market_data.get_market_session",
                side_effect=lambda _ts: session,
            ),
        ):
            return quotes_mod._yf_quote_sync("AAPL")

    def test_pre_session_uses_bar_close(self, hist_pre: pd.DataFrame) -> None:
        result = self._run_with(hist_pre, "pre")
        assert result["session"] == "pre"
        assert result["price"] == pytest.approx(289.35)
        assert result["previous_close"] == pytest.approx(287.40)

    def test_pre_session_prev_close_ignores_prepost_bar(
        self, hist_pre: pd.DataFrame
    ) -> None:
        """Regression: prepost=True means hist[-2] is itself a prepost bar,
        not yesterday's RTH close. previous_close must come from info, not
        from the second-to-last hist row."""
        result = self._run_with(hist_pre, "pre")
        # If the code mistakenly used hist[-2].Close, prev_close would be 287.10.
        assert result["previous_close"] != pytest.approx(287.10)
        assert result["previous_close"] == pytest.approx(287.40)

    def test_regular_session_uses_info_price(self, hist_pre: pd.DataFrame) -> None:
        result = self._run_with(hist_pre, "regular")
        assert result["session"] == "regular"
        assert result["price"] == pytest.approx(287.51)

    def test_post_session_uses_bar_close(self) -> None:
        hist = _make_hist(
            [
                ("2026-05-07 16:30", 291.10, 700),
                ("2026-05-07 18:00", 292.40, 800),
            ]
        )
        result = self._run_with(hist, "post")
        assert result["session"] == "post"
        assert result["price"] == pytest.approx(292.40)

    def test_closed_session_uses_info_price(self) -> None:
        hist = _make_hist(
            [
                ("2026-05-04 12:00", 285.00, 1000),
                ("2026-05-04 14:00", 286.00, 1000),
            ]
        )
        result = self._run_with(hist, "closed")
        assert result["session"] == "closed"
        assert result["price"] == pytest.approx(287.51)

    def test_prev_close_falls_back_to_hist_when_info_empty(self) -> None:
        """When ticker.info has no previous-close keys, fall back to hist[-2]."""
        hist = _make_hist(
            [
                ("2026-05-06 12:00", 280.00, 5000),
                ("2026-05-07 12:00", 285.00, 5000),
            ]
        )
        result = self._run_with(hist, "regular", info={})
        assert result["previous_close"] == pytest.approx(280.00)
        # No info price keys → fallback to last hist Close.
        assert result["price"] == pytest.approx(285.00)
