"""W3.8 unit tests — SEC EDGAR Form 4 atom feed fetcher.

Coverage:

* ``get_user_agent`` honours ``SEC_EDGAR_USER_AGENT`` env var and falls
  back to PRD D4 default ``ffffhhhww@qq.com`` when missing/empty.
* ``Form4Client`` pins the User-Agent header on every request — SEC
  rejects requests without one, and the default is mandated by D4.
* CIK lookup uses ``files/company_tickers.json``, returns 10-digit
  zero-padded CIKs, caches the map across calls (one fetch only),
  and returns ``None`` for unknown symbols.
* ``fetch_form4_atom`` URL-formats the CIK + count correctly and
  returns the raw atom body verbatim.
* Token-bucket keeps 50 sequential requests under the 10 req/s
  ceiling per PRD AC #5 — measured at 9 rps with the default rate.

Tests use ``httpx.MockTransport`` so we never hit the real SEC.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest

from src.agent.tools.sec_edgar.form4 import (
    ATOM_FEED_URL,
    DEFAULT_USER_AGENT,
    Form4Client,
    TICKER_MAP_URL,
    get_user_agent,
)


# ---------------------------------------------------------------------------
# get_user_agent
# ---------------------------------------------------------------------------


def test_get_user_agent_defaults_to_d4_ffffhhhww(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)
    assert get_user_agent() == DEFAULT_USER_AGENT
    assert DEFAULT_USER_AGENT == "ffffhhhww@qq.com"


def test_get_user_agent_honours_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "research@example.com")
    assert get_user_agent() == "research@example.com"


def test_get_user_agent_falls_back_when_env_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    """D4: 'If env missing, fall back to default (do NOT fail fast).'
    Treat a whitespace-only env value the same as missing."""
    monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "   ")
    assert get_user_agent() == DEFAULT_USER_AGENT


# ---------------------------------------------------------------------------
# Test fixtures: a deterministic SEC mock transport
# ---------------------------------------------------------------------------


_TICKER_MAP_BODY = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA Corp"},
}

_AAPL_FORM4_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Form 4 — Apple Inc.</title>
  <entry>
    <title>4 - Cook Timothy D (Reporting)</title>
    <updated>2026-05-07T16:00:00-04:00</updated>
  </entry>
</feed>
"""


def _make_handler(captured_headers: list[dict[str, str]] | None = None,
                  request_log: list[str] | None = None):
    def _handler(request: httpx.Request) -> httpx.Response:
        if captured_headers is not None:
            captured_headers.append(dict(request.headers))
        if request_log is not None:
            request_log.append(str(request.url))
        if str(request.url) == TICKER_MAP_URL:
            return httpx.Response(200, json=_TICKER_MAP_BODY)
        # Atom feed for any CIK
        if "browse-edgar" in str(request.url):
            return httpx.Response(
                200,
                text=_AAPL_FORM4_ATOM,
                headers={"Content-Type": "application/atom+xml"},
            )
        return httpx.Response(404, text="not mocked")

    return _handler


# ---------------------------------------------------------------------------
# Form4Client.lookup_cik
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lookup_cik_returns_zero_padded_10_digit_string() -> None:
    transport = httpx.MockTransport(_make_handler())
    async with Form4Client(transport=transport) as client:
        cik = await client.lookup_cik("AAPL")
        assert cik == "0000320193"
        cik2 = await client.lookup_cik("NVDA")
        assert cik2 == "0001045810"


@pytest.mark.asyncio
async def test_lookup_cik_case_insensitive_on_symbol() -> None:
    transport = httpx.MockTransport(_make_handler())
    async with Form4Client(transport=transport) as client:
        assert await client.lookup_cik("aapl") == "0000320193"


@pytest.mark.asyncio
async def test_lookup_cik_returns_none_for_unknown_symbol() -> None:
    transport = httpx.MockTransport(_make_handler())
    async with Form4Client(transport=transport) as client:
        assert await client.lookup_cik("UNKNOWN_TICKER_XYZ") is None


@pytest.mark.asyncio
async def test_lookup_cik_caches_ticker_map_across_calls() -> None:
    """Second lookup must NOT re-hit the tickers endpoint — that map
    is ~30k rows and EDGAR's rate limit is per-IP. One fetch per
    process lifetime is the right shape."""
    request_log: list[str] = []
    transport = httpx.MockTransport(_make_handler(request_log=request_log))
    async with Form4Client(transport=transport) as client:
        await client.lookup_cik("AAPL")
        await client.lookup_cik("NVDA")
        await client.lookup_cik("AAPL")
        # Exactly one ticker-map fetch.
        ticker_hits = [u for u in request_log if u == TICKER_MAP_URL]
        assert len(ticker_hits) == 1


# ---------------------------------------------------------------------------
# User-Agent header
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_form4_client_sends_default_user_agent_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)
    captured: list[dict[str, str]] = []
    transport = httpx.MockTransport(_make_handler(captured_headers=captured))
    async with Form4Client(transport=transport) as client:
        await client.lookup_cik("AAPL")
    assert captured, "no requests captured"
    for hdrs in captured:
        assert hdrs.get("user-agent") == DEFAULT_USER_AGENT


@pytest.mark.asyncio
async def test_form4_client_honours_explicit_user_agent_arg() -> None:
    captured: list[dict[str, str]] = []
    transport = httpx.MockTransport(_make_handler(captured_headers=captured))
    async with Form4Client(user_agent="explicit@example.com", transport=transport) as client:
        await client.lookup_cik("AAPL")
    assert captured[0].get("user-agent") == "explicit@example.com"


# ---------------------------------------------------------------------------
# fetch_form4_atom
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_form4_atom_returns_raw_xml_body() -> None:
    transport = httpx.MockTransport(_make_handler())
    async with Form4Client(transport=transport) as client:
        out = await client.fetch_form4_atom("AAPL", count=5)
        assert out is not None
        assert "<feed" in out
        assert "Cook Timothy D" in out


@pytest.mark.asyncio
async def test_fetch_form4_atom_url_carries_padded_cik_and_count() -> None:
    request_log: list[str] = []
    transport = httpx.MockTransport(_make_handler(request_log=request_log))
    async with Form4Client(transport=transport) as client:
        await client.fetch_form4_atom("AAPL", count=7)
    atom_calls = [u for u in request_log if "browse-edgar" in u]
    assert len(atom_calls) == 1
    assert "CIK=0000320193" in atom_calls[0]
    assert "count=7" in atom_calls[0]
    assert "type=4" in atom_calls[0]


@pytest.mark.asyncio
async def test_fetch_form4_atom_clamps_count_into_legal_range() -> None:
    """SEC accepts 1..100; we clamp before the URL templating."""
    request_log: list[str] = []
    transport = httpx.MockTransport(_make_handler(request_log=request_log))
    async with Form4Client(transport=transport) as client:
        await client.fetch_form4_atom("AAPL", count=0)
        await client.fetch_form4_atom("AAPL", count=999)
    atom_calls = [u for u in request_log if "browse-edgar" in u]
    assert "count=1" in atom_calls[0]
    assert "count=100" in atom_calls[1]


@pytest.mark.asyncio
async def test_fetch_form4_atom_returns_none_for_unknown_symbol() -> None:
    request_log: list[str] = []
    transport = httpx.MockTransport(_make_handler(request_log=request_log))
    async with Form4Client(transport=transport) as client:
        out = await client.fetch_form4_atom("UNKNOWN_TICKER_XYZ")
    assert out is None
    # Ticker map fetched once; atom never fetched.
    assert any("browse-edgar" in u for u in request_log) is False


@pytest.mark.asyncio
async def test_fetch_form4_atom_url_format_constant_matches_use() -> None:
    """Pin the URL template — the exact path / query string is the
    SEC contract; renaming or losing a parameter would silently break
    real fetches."""
    assert "browse-edgar" in ATOM_FEED_URL
    assert "{cik}" in ATOM_FEED_URL
    assert "type=4" in ATOM_FEED_URL
    assert "{count}" in ATOM_FEED_URL
    assert "output=atom" in ATOM_FEED_URL


# ---------------------------------------------------------------------------
# Rate-limit (PRD AC #5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limiter_holds_50_sequential_requests_under_10_per_sec() -> None:
    """PRD AC #5: 50 sequential SEC requests stay under 10/s. We pick
    a deterministic mock so the test measures the bucket, not the
    network."""
    transport = httpx.MockTransport(_make_handler())
    # Use the production default rate.
    async with Form4Client(transport=transport) as client:
        # Pre-fill the ticker map so the timing window measures only
        # the atom-feed calls.
        await client.lookup_cik("AAPL")
        start = time.monotonic()
        for _ in range(50):
            out = await client.fetch_form4_atom("AAPL", count=5)
            assert out is not None
        elapsed = time.monotonic() - start
    rps = 50 / elapsed
    assert rps < 10.0, (
        f"rate limiter let through {rps:.2f} req/s, AC #5 ceiling is 10/s"
    )


@pytest.mark.asyncio
async def test_rate_limiter_can_be_overridden_for_tests() -> None:
    """A high rate makes test runs fast; the default rate is the
    production safety value."""
    transport = httpx.MockTransport(_make_handler())
    async with Form4Client(transport=transport, rate_per_sec=1000.0) as client:
        await client.lookup_cik("AAPL")
        start = time.monotonic()
        for _ in range(20):
            await client.fetch_form4_atom("AAPL", count=5)
        elapsed = time.monotonic() - start
    # Should be well under one second on any sane machine.
    assert elapsed < 1.0


# ---------------------------------------------------------------------------
# HTTP error propagation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_form4_atom_raises_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TICKER_MAP_URL:
            return httpx.Response(200, json=_TICKER_MAP_BODY)
        return httpx.Response(503, text="EDGAR overloaded")

    transport = httpx.MockTransport(handler)
    async with Form4Client(transport=transport) as client:
        await client.lookup_cik("AAPL")  # warm cache
        with pytest.raises(httpx.HTTPStatusError):
            await client.fetch_form4_atom("AAPL", count=5)
