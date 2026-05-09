"""W3.18 — unit tests for `_extended_hours_companion`.

The helper picks an after-hours / pre-market companion price to render
*alongside* a regular- or closed-session primary price (typical
weekend / Monday-morning UX). Cousin tests for the existing
`_extended_hours_price` helper live in test_extended_hours_price.py;
keeping these separate so the W3.18 contract is auditable on its own.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.services.data_manager.manager import _extended_hours_companion


NOW = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)  # Saturday noon UTC


def _epoch(dt: datetime) -> int:
    return int(dt.timestamp())


class TestPrimarySessionGate:
    def test_returns_none_during_active_pre_session(self) -> None:
        info = {
            "postMarketPrice": 215.05,
            "postMarketTime": _epoch(NOW - timedelta(hours=2)),
        }
        assert (
            _extended_hours_companion(
                info, primary_session="pre", primary_price=214.80,
                previous_close=215.20, now=NOW,
            )
            is None
        ), "primary IS the ext-hours print during pre — companion redundant"

    def test_returns_none_during_active_post_session(self) -> None:
        info = {
            "postMarketPrice": 215.05,
            "postMarketTime": _epoch(NOW - timedelta(hours=1)),
        }
        assert (
            _extended_hours_companion(
                info, primary_session="post", primary_price=215.05,
                previous_close=215.20, now=NOW,
            )
            is None
        )

    def test_runs_during_regular_session(self) -> None:
        # Mid-session occurrence — pre-market companion still relevant
        # for "the morning gap held / faded" UX.
        info = {
            "preMarketPrice": 214.80,
            "preMarketTime": _epoch(NOW - timedelta(hours=4)),
        }
        result = _extended_hours_companion(
            info, primary_session="regular", primary_price=215.20,
            previous_close=213.10, now=NOW,
        )
        assert result is not None
        price, session, _pct, _asof = result
        assert session == "pre"
        assert price == pytest.approx(214.80)


class TestFreshnessGate:
    def test_post_companion_within_18h_accepted(self) -> None:
        # Friday 16:30 ET close → Saturday 12:00 UTC = ~17h later.
        post_ts = NOW - timedelta(hours=17)
        info = {"postMarketPrice": 215.05, "postMarketTime": _epoch(post_ts)}
        result = _extended_hours_companion(
            info, primary_session="closed", primary_price=215.20,
            previous_close=213.10, now=NOW,
        )
        assert result is not None
        assert result[1] == "post"

    def test_post_companion_older_than_18h_rejected(self) -> None:
        # Stale Friday AH on Monday 09:00 (~64h later) — must NOT show.
        post_ts = NOW - timedelta(hours=20)
        info = {"postMarketPrice": 215.05, "postMarketTime": _epoch(post_ts)}
        assert (
            _extended_hours_companion(
                info, primary_session="closed", primary_price=215.20,
                previous_close=213.10, now=NOW,
            )
            is None
        )

    def test_pre_companion_within_6h_accepted(self) -> None:
        pre_ts = NOW - timedelta(hours=4)
        info = {"preMarketPrice": 214.80, "preMarketTime": _epoch(pre_ts)}
        result = _extended_hours_companion(
            info, primary_session="regular", primary_price=215.20,
            previous_close=213.10, now=NOW,
        )
        assert result is not None
        assert result[1] == "pre"

    def test_pre_companion_older_than_6h_rejected(self) -> None:
        pre_ts = NOW - timedelta(hours=8)
        info = {"preMarketPrice": 214.80, "preMarketTime": _epoch(pre_ts)}
        assert (
            _extended_hours_companion(
                info, primary_session="regular", primary_price=215.20,
                previous_close=213.10, now=NOW,
            )
            is None
        )


class TestPriceComputation:
    def test_change_percent_vs_primary_not_prev_close(self) -> None:
        # Primary 215.20, AH 215.05 → -0.0697% vs primary.
        # If the helper mistakenly used previous_close=213.10 as base,
        # the pct would be (+0.916%), so the assertion below catches
        # that bug.
        info = {
            "postMarketPrice": 215.05,
            "postMarketTime": _epoch(NOW - timedelta(hours=17)),
        }
        result = _extended_hours_companion(
            info, primary_session="closed", primary_price=215.20,
            previous_close=213.10, now=NOW,
        )
        assert result is not None
        _price, _session, pct, _asof = result
        expected = (215.05 - 215.20) / 215.20 * 100.0
        assert pct == pytest.approx(expected)
        assert pct < 0  # negative move

    def test_zero_or_negative_primary_price_returns_none(self) -> None:
        info = {
            "postMarketPrice": 215.05,
            "postMarketTime": _epoch(NOW - timedelta(hours=2)),
        }
        assert (
            _extended_hours_companion(
                info, primary_session="closed", primary_price=0.0,
                previous_close=213.10, now=NOW,
            )
            is None
        )

    def test_asof_carried_through_from_info(self) -> None:
        post_ts = NOW - timedelta(hours=17)
        info = {"postMarketPrice": 215.05, "postMarketTime": _epoch(post_ts)}
        result = _extended_hours_companion(
            info, primary_session="closed", primary_price=215.20,
            previous_close=213.10, now=NOW,
        )
        assert result is not None
        _p, _s, _pct, asof = result
        # Allow second-resolution drift from epoch round-trip.
        assert abs((asof - post_ts).total_seconds()) < 2


class TestEdgeCases:
    def test_none_info_returns_none(self) -> None:
        assert (
            _extended_hours_companion(
                None, primary_session="closed", primary_price=215.20,
                previous_close=213.10, now=NOW,
            )
            is None
        )

    def test_empty_info_returns_none(self) -> None:
        assert (
            _extended_hours_companion(
                {}, primary_session="closed", primary_price=215.20,
                previous_close=213.10, now=NOW,
            )
            is None
        )

    def test_zero_post_price_rejected(self) -> None:
        # yfinance occasionally returns 0.0 for fields it doesn't have.
        info = {
            "postMarketPrice": 0.0,
            "postMarketTime": _epoch(NOW - timedelta(hours=2)),
        }
        assert (
            _extended_hours_companion(
                info, primary_session="closed", primary_price=215.20,
                previous_close=213.10, now=NOW,
            )
            is None
        )

    def test_missing_timestamp_rejected(self) -> None:
        info = {"postMarketPrice": 215.05}  # no postMarketTime
        assert (
            _extended_hours_companion(
                info, primary_session="closed", primary_price=215.20,
                previous_close=213.10, now=NOW,
            )
            is None
        )

    def test_unparseable_timestamp_rejected(self) -> None:
        info = {
            "postMarketPrice": 215.05,
            "postMarketTime": "not-a-number",
        }
        assert (
            _extended_hours_companion(
                info, primary_session="closed", primary_price=215.20,
                previous_close=213.10, now=NOW,
            )
            is None
        )

    def test_picks_most_recent_when_both_pre_and_post_fresh(self) -> None:
        # Both within their TTLs — prefer the more recent timestamp.
        post_ts = NOW - timedelta(hours=10)
        pre_ts = NOW - timedelta(hours=2)
        info = {
            "postMarketPrice": 215.05,
            "postMarketTime": _epoch(post_ts),
            "preMarketPrice": 214.80,
            "preMarketTime": _epoch(pre_ts),
        }
        result = _extended_hours_companion(
            info, primary_session="regular", primary_price=215.20,
            previous_close=213.10, now=NOW,
        )
        assert result is not None
        assert result[1] == "pre"  # pre is more recent
        assert result[0] == pytest.approx(214.80)
