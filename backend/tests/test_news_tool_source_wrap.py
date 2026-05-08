"""W3.4 unit tests — news tools emit Source-style footnotes.

Two news tools, two patterns:

  finnhub_news (DataManager-backed; provider = finnhub primary):
    Last line ::= "Source: finnhub [FH-N-AAPL-2026-05-09] asof <iso>"

  get_news_sentiment (AlphaVantage-only):
    Last line ::= "Source: alphavantage [AV-N-AAPL-2026-05-09] asof <iso>"

asof comes from the latest headline timestamp, NOT now() — a stale 5-day-
old news bucket should still be recognizable as 5 days old in the footnote
when the LLM cites it tomorrow. These tests pin the format and that the
asof actually tracks the freshest headline.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agent.tools.alpha_vantage.news import (
    _av_news_latest_asof,
    create_news_tools,
)
from src.agent.tools.finnhub.news import (
    _news_source_id,
    create_finnhub_news_tool,
)


# ---------------------------------------------------------------------------
# _news_source_id helper
# ---------------------------------------------------------------------------


def test_news_source_id_finnhub_prefix() -> None:
    asof = datetime(2026, 5, 9, 18, 35, tzinfo=UTC)
    assert _news_source_id("finnhub", "aapl", asof) == "FH-N-AAPL-2026-05-09"


def test_news_source_id_alphavantage_prefix() -> None:
    asof = datetime(2026, 5, 9, tzinfo=UTC)
    assert _news_source_id("alphavantage", "MSFT", asof) == "AV-N-MSFT-2026-05-09"


def test_news_source_id_unknown_provider_uses_uppercased() -> None:
    asof = datetime(2026, 5, 9, tzinfo=UTC)
    assert _news_source_id("custom_feed", "AAPL", asof) == "CUSTOM_FEED-N-AAPL-2026-05-09"


# ---------------------------------------------------------------------------
# _av_news_latest_asof helper
# ---------------------------------------------------------------------------


def test_av_news_latest_asof_picks_newest_headline() -> None:
    data = {
        "feed": [
            {"time_published": "20260507T120000"},
            {"time_published": "20260509T140000"},  # latest
            {"time_published": "20260508T093000"},
        ]
    }
    latest = _av_news_latest_asof(data)
    assert latest is not None
    assert latest.year == 2026 and latest.month == 5 and latest.day == 9
    assert latest.hour == 14


def test_av_news_latest_asof_skips_malformed_entries() -> None:
    data = {
        "feed": [
            {"time_published": "20260509T120000"},  # only valid
            {"time_published": ""},
            {"time_published": "garbage"},
            {},  # missing field
        ]
    }
    latest = _av_news_latest_asof(data)
    assert latest is not None
    assert latest.day == 9


def test_av_news_latest_asof_returns_none_on_empty_feed() -> None:
    assert _av_news_latest_asof({}) is None
    assert _av_news_latest_asof({"feed": []}) is None


# ---------------------------------------------------------------------------
# finnhub_news tool
# ---------------------------------------------------------------------------


def _news_item(date: datetime, title: str, source: str) -> SimpleNamespace:
    return SimpleNamespace(date=date, title=title, source=source)


def _make_finnhub_tool(items: list[Any]) -> Any:  # noqa: ANN401
    dm = MagicMock()
    dm.get_company_news = AsyncMock(return_value=items)
    return create_finnhub_news_tool(dm)[0]


@pytest.mark.asyncio
async def test_finnhub_news_emits_footnote_with_latest_headline_date() -> None:
    items = [
        _news_item(datetime(2026, 5, 7, 12, 0, tzinfo=UTC), "Older", "Reuters"),
        _news_item(datetime(2026, 5, 9, 14, 30, tzinfo=UTC), "Newest", "Bloomberg"),
        _news_item(datetime(2026, 5, 8, 9, 0, tzinfo=UTC), "Mid", "WSJ"),
    ]
    tool = _make_finnhub_tool(items)
    out = await tool.ainvoke({"symbol": "AAPL", "days": 7})

    # Footnote: "Source: finnhub [FH-N-AAPL-2026-05-09] asof 2026-05-09T14:30Z"
    assert "Source: finnhub [FH-N-AAPL-2026-05-09]" in out
    assert "asof 2026-05-09T14:30Z" in out
    # Body still renders the per-headline (publisher) for the reader.
    assert "(Bloomberg)" in out


@pytest.mark.asyncio
async def test_finnhub_news_emits_no_footnote_when_no_items() -> None:
    tool = _make_finnhub_tool([])
    out = await tool.ainvoke({"symbol": "TSLA", "days": 7})
    assert "No recent news found" in out
    assert "Source:" not in out


@pytest.mark.asyncio
async def test_finnhub_news_emits_no_footnote_on_provider_failure() -> None:
    # If DataManager raises, the tool returns an error string — no
    # footnote (the Phase2 prompt's consistency_gate would otherwise
    # cite a "source" we never actually fetched from).
    dm = MagicMock()
    dm.get_company_news = AsyncMock(side_effect=RuntimeError("finnhub down"))
    tool = create_finnhub_news_tool(dm)[0]
    out = await tool.ainvoke({"symbol": "NVDA", "days": 7})
    assert "Failed to fetch news" in out
    assert "Source:" not in out


# ---------------------------------------------------------------------------
# get_news_sentiment (AlphaVantage) tool
# ---------------------------------------------------------------------------


def _make_av_news_tool(av_response: dict[str, Any]) -> Any:  # noqa: ANN401
    service = MagicMock()
    service.get_news_sentiment = AsyncMock(return_value=av_response)
    formatter = MagicMock()
    formatter.format_news_sentiment = MagicMock(return_value="AV NEWS BODY")
    return create_news_tools(service, formatter)[0]


@pytest.mark.asyncio
async def test_av_news_sentiment_emits_alphavantage_footnote() -> None:
    response = {
        "feed": [
            {"time_published": "20260507T120000", "title": "Older"},
            {"time_published": "20260509T143000", "title": "Latest"},
        ]
    }
    tool = _make_av_news_tool(response)
    out = await tool.ainvoke({"symbol": "AAPL"})

    assert out.startswith("AV NEWS BODY")
    assert "Source: alphavantage [AV-N-AAPL-2026-05-09]" in out
    assert "asof 2026-05-09T14:30Z" in out


@pytest.mark.asyncio
async def test_av_news_sentiment_emits_no_footnote_when_feed_empty() -> None:
    tool = _make_av_news_tool({"feed": []})
    out = await tool.ainvoke({"symbol": "TSLA"})
    assert "No news sentiment data available" in out
    assert "Source:" not in out
