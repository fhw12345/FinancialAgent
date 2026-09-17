"""Completed XNYS sessions, including holidays/early closes, from a pinned calendar."""

from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any

import exchange_calendars as xcals
import pandas as pd


@lru_cache(maxsize=8)
def calendar(year: int) -> Any:
    return xcals.get_calendar("XNYS", start=f"{year-2}-01-01", end=f"{year+1}-12-31")


def completed_session(now: datetime) -> date:
    cal = calendar(now.year)
    schedule = cal.schedule.loc[
        str((now - timedelta(days=15)).date()) : str(now.date())
    ]
    closed = schedule[schedule["close"] <= pd.Timestamp(now)]
    if closed.empty:
        raise ValueError("No completed XNYS session")
    result: date = closed.index[-1].date()
    return result


def sessions(as_of: date, count: int = 60) -> list[date]:
    cal = calendar(as_of.year)
    if not cal.is_session(pd.Timestamp(as_of)):
        raise ValueError("Not an XNYS session")
    return [
        s.date()
        for s in cal.sessions_in_range(as_of - timedelta(days=250), as_of)[-count:]
    ]
