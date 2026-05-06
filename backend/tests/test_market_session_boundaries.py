"""Boundary tests for get_market_session().

US/Eastern session windows:
  pre:     04:00 .. 09:30
  regular: 09:30 .. 16:00
  post:    16:00 .. 20:00
  closed:  everything else, plus weekends
"""

import pandas as pd
import pytest

from src.services.market_data import get_market_session


def _et(date: str, hh: int, mm: int) -> pd.Timestamp:
    return pd.Timestamp(f"{date} {hh:02d}:{mm:02d}").tz_localize("America/New_York")


@pytest.mark.parametrize(
    "ts,expected",
    [
        # Wednesday 2026-05-06 — a regular weekday
        (_et("2026-05-06", 3, 59), "closed"),
        (_et("2026-05-06", 4, 0), "pre"),
        (_et("2026-05-06", 9, 29), "pre"),
        (_et("2026-05-06", 9, 30), "regular"),
        (_et("2026-05-06", 15, 59), "regular"),
        (_et("2026-05-06", 16, 0), "post"),
        (_et("2026-05-06", 19, 59), "post"),
        (_et("2026-05-06", 20, 0), "closed"),
        (_et("2026-05-06", 23, 59), "closed"),
        # Saturday 2026-05-09 — weekend always closed
        (_et("2026-05-09", 10, 0), "closed"),
        # Sunday 2026-05-10 — weekend always closed
        (_et("2026-05-10", 14, 0), "closed"),
    ],
)
def test_session_boundaries(ts: pd.Timestamp, expected: str) -> None:
    assert get_market_session(ts) == expected


def test_naive_timestamp_assumed_utc() -> None:
    # 14:00 UTC on 2026-05-06 == 10:00 ET → regular
    naive = pd.Timestamp("2026-05-06 14:00")
    assert get_market_session(naive) == "regular"


def test_utc_timestamp_converts_correctly() -> None:
    # 03:00 UTC == 23:00 ET previous day (Tuesday) → closed
    utc = pd.Timestamp("2026-05-06 03:00", tz="UTC")
    assert get_market_session(utc) == "closed"
    # 13:30 UTC == 09:30 ET → regular
    utc = pd.Timestamp("2026-05-06 13:30", tz="UTC")
    assert get_market_session(utc) == "regular"
