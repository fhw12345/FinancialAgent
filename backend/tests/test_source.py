"""W3.1 unit tests for the Source provenance model."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.models.source import Source


# ---------------------------------------------------------------------------
# Construction + field shapes
# ---------------------------------------------------------------------------


def test_source_accepts_float_value() -> None:
    s = Source(
        value=24.5,
        source="alphavantage",
        asof=datetime(2026, 5, 9, tzinfo=timezone.utc),
        url="https://www.alphavantage.co/query?function=OVERVIEW&symbol=AAPL",
    )
    assert s.value == 24.5
    assert s.source == "alphavantage"
    assert s.url is not None and s.url.startswith("https://")


def test_source_accepts_string_value() -> None:
    # News headlines, Form 4 plan_type strings, etc.
    s = Source(
        value="10b5-1",
        source="sec_edgar_form4",
        asof=datetime(2026, 1, 15, tzinfo=timezone.utc),
    )
    assert s.value == "10b5-1"
    assert s.url is None


def test_source_accepts_dict_value() -> None:
    # Insider transaction or news article — tool wrappers will pack the
    # whole record into Source.value when partial-attribution is impractical.
    payload = {"insider": "Jensen Huang", "shares": 1000, "code": "S"}
    s = Source(
        value=payload,
        source="sec_edgar_form4",
        asof=datetime(2026, 5, 1, tzinfo=timezone.utc),
        url="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany",
    )
    assert s.value == payload


def test_source_id_optional() -> None:
    s = Source(
        value=100.0,
        source="yfinance",
        asof=datetime(2026, 5, 9, tzinfo=timezone.utc),
    )
    assert s.id is None
    # Falls back to source name in the label.
    assert s.short_label() == "yfinance"


def test_source_id_used_in_short_label() -> None:
    s = Source(
        value=24.5,
        source="alphavantage",
        asof=datetime(2026, 5, 9, tzinfo=timezone.utc),
        id="AV-PE-AAPL-2026-05-09",
    )
    assert s.short_label() == "AV-PE-AAPL-2026-05-09"


# ---------------------------------------------------------------------------
# Source-name normalization
# ---------------------------------------------------------------------------


def test_source_name_normalized_to_lower_stripped() -> None:
    s = Source(
        value=1.0,
        source="  AlphaVantage  ",
        asof=datetime(2026, 5, 9, tzinfo=timezone.utc),
    )
    assert s.source == "alphavantage"


def test_source_name_required() -> None:
    # Empty source means the consistency gate has nothing to match.
    with pytest.raises(ValidationError):
        Source(
            value=1.0,
            source="",
            asof=datetime(2026, 5, 9, tzinfo=timezone.utc),
        )


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------


def test_url_must_be_http_or_https() -> None:
    with pytest.raises(ValidationError, match="http"):
        Source(
            value=1.0,
            source="custom",
            asof=datetime(2026, 5, 9, tzinfo=timezone.utc),
            url="ftp://example.com/data",
        )


def test_url_blank_string_normalizes_to_none() -> None:
    # Tool wrappers occasionally pass through "" when the upstream API
    # returns an empty link field. Treat that as "no URL" rather than
    # rendering a broken footnote.
    s = Source(
        value=1.0,
        source="yfinance",
        asof=datetime(2026, 5, 9, tzinfo=timezone.utc),
        url="   ",
    )
    assert s.url is None


def test_url_optional_with_none() -> None:
    s = Source(
        value=1.0,
        source="yfinance",
        asof=datetime(2026, 5, 9, tzinfo=timezone.utc),
        url=None,
    )
    assert s.url is None


# ---------------------------------------------------------------------------
# Round-trip via model_dump (Phase2 persistence path)
# ---------------------------------------------------------------------------


def test_model_dump_json_mode_roundtrips() -> None:
    # The decision-persistence path calls model_dump(mode="json") so
    # asof must serialize cleanly without losing tz info.
    asof = datetime(2026, 5, 9, 14, 30, tzinfo=timezone.utc)
    s = Source(
        value=24.5,
        source="alphavantage",
        asof=asof,
        url="https://www.alphavantage.co/query",
        id="AV-PE-AAPL-2026-05-09",
    )
    dumped = s.model_dump(mode="json")
    assert dumped["value"] == 24.5
    assert dumped["source"] == "alphavantage"
    assert dumped["asof"].startswith("2026-05-09T14:30:00")
    assert dumped["url"] == "https://www.alphavantage.co/query"
    assert dumped["id"] == "AV-PE-AAPL-2026-05-09"

    # And the JSON shape parses back unchanged.
    rebuilt = Source.model_validate(dumped)
    assert rebuilt.value == s.value
    assert rebuilt.source == s.source
    assert rebuilt.asof == s.asof
    assert rebuilt.url == s.url
    assert rebuilt.id == s.id


def test_asof_required() -> None:
    with pytest.raises(ValidationError):
        Source(value=1.0, source="yfinance")  # type: ignore[call-arg]
