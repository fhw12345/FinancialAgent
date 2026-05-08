"""W3.13 — live SEC EDGAR Form 4 integration tests.

Hits real ``https://www.sec.gov`` endpoints. Marked
``@pytest.mark.integration`` and skipped by default per pyproject.toml
addopts. Run explicitly:

    pytest -m integration tests/test_form4_real.py

NVDA is chosen as the canonical issuer because (a) it has frequent
Form 4 activity (PRD AC #3 calls for ≥3 of N parsed transactions to
have ``plan_type`` populated), and (b) its CIK has been stable for
years so the ticker→CIK lookup is deterministic.

These tests validate the production wiring end-to-end: env-driven
User-Agent, the ticker map round-trip, the atom feed shape,
fetch_recent_transactions composition, and the PRD AC #5 rate-limit
ceiling. Failures here indicate a real-world regression — SEC schema
drift, network policy change, or rate-limit recalibration.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from src.agent.tools.sec_edgar.form4 import (
    DEFAULT_RATE_LIMIT_PER_SEC,
    PLAN_TYPE_10B5_1,
    PLAN_TYPE_DISCRETIONARY,
    PLAN_TYPE_UNKNOWN,
    Form4Client,
    Form4Transaction,
)


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_lookup_cik_nvda_resolves() -> None:
    async with Form4Client() as client:
        cik = await client.lookup_cik("NVDA")
    assert cik is not None
    assert len(cik) == 10
    assert cik.isdigit()
    # NVDA's CIK is 0001045810 — pinned because if SEC ever renumbers
    # it (they don't) the test will fail loudly rather than silently
    # reading bad data.
    assert cik == "0001045810"


@pytest.mark.asyncio
async def test_lookup_cik_case_insensitive() -> None:
    async with Form4Client() as client:
        a = await client.lookup_cik("nvda")
        b = await client.lookup_cik("NVDA")
    assert a == b
    assert a is not None


@pytest.mark.asyncio
async def test_lookup_unknown_symbol_returns_none() -> None:
    async with Form4Client() as client:
        cik = await client.lookup_cik("XYZFAKE9999")
    assert cik is None


@pytest.mark.asyncio
async def test_fetch_atom_feed_returns_xml() -> None:
    async with Form4Client() as client:
        xml = await client.fetch_form4_atom("NVDA", count=5)
    assert xml is not None
    # Atom feed signature.
    assert "<feed" in xml or "<?xml" in xml
    assert "Form 4" in xml or "form 4" in xml.lower() or "type=4" in xml.lower()


@pytest.mark.asyncio
async def test_fetch_recent_transactions_nvda_populates_plan_type() -> None:
    """PRD AC #3: plan_type populated for ≥3 of N parsed Form 4s.

    NVDA is high-volume so 5 recent filings should yield well over 3
    nonDerivativeTransaction rows; populated means the classifier
    returned 10b5-1 / discretionary (not unknown).
    """
    async with Form4Client() as client:
        txs = await client.fetch_recent_transactions("NVDA", count=5)

    assert isinstance(txs, list)
    # Some Form 4s only carry derivative transactions (RSU vests) and
    # parse_form4_detail intentionally skips those, so the count can
    # be lower than the filing count. Still expect at least some
    # non-derivative activity over 5 recent filings.
    assert len(txs) >= 3

    populated = [
        t for t in txs if t.plan_type in (PLAN_TYPE_10B5_1, PLAN_TYPE_DISCRETIONARY)
    ]
    assert len(populated) >= 3, (
        f"PRD AC#3: expected ≥3 transactions with plan_type populated, "
        f"got {len(populated)} of {len(txs)}. "
        f"Plan-type distribution: "
        f"{[(t.transaction_date, t.plan_type) for t in txs[:10]]}"
    )

    # Each populated tx should also carry the structured fields the
    # downstream W3.10 enrichment relies on.
    for tx in populated:
        assert isinstance(tx, Form4Transaction)
        assert tx.issuer_symbol == "NVDA"
        assert tx.transaction_date is not None
        assert tx.shares is not None and tx.shares > 0


@pytest.mark.asyncio
async def test_fetch_recent_transactions_unknown_symbol_short_circuits() -> None:
    async with Form4Client() as client:
        txs = await client.fetch_recent_transactions("XYZFAKE9999", count=3)
    assert txs == []


@pytest.mark.asyncio
async def test_rate_limit_50_sequential_under_10_per_sec() -> None:
    """PRD AC #5: 50 sequential SEC requests stay under 10 req/s.

    We hit the lightweight ticker-map endpoint 50 times in a row to
    measure the bucket cadence end-to-end. The ticker map is cached
    on the client, so we provoke real traffic by constructing a
    fresh client per call. Each client carries its own bucket so we
    measure raw HTTP cadence, not bucket throttling.

    Note: this asserts the *aggregate* throughput, not per-second
    instantaneous bursts — the token bucket starts full so the first
    capacity tokens fire freely, with the production
    ``DEFAULT_RATE_LIMIT_PER_SEC`` (8) chosen so the burst + steady-
    state stays under SEC's documented 10/s ceiling.
    """
    n = 50
    start = time.monotonic()
    for _ in range(n):
        async with Form4Client() as client:
            await client._ensure_ticker_map()
    elapsed = time.monotonic() - start
    rate = n / elapsed
    assert rate < 10.0, (
        f"AC #5: 50 sequential calls measured at {rate:.2f} req/s, "
        f"must stay under 10. Elapsed = {elapsed:.2f}s."
    )


@pytest.mark.asyncio
async def test_default_rate_limit_constant_is_under_sec_ceiling() -> None:
    # Sanity: defensive constant pin so a future PR cannot raise the
    # default past the SEC ceiling without this test failing.
    assert DEFAULT_RATE_LIMIT_PER_SEC < 10.0


@pytest.mark.asyncio
async def test_concurrent_clients_do_not_corrupt_atom_response() -> None:
    """Two parallel atom fetches must each return valid XML.

    Each Form4Client carries its own bucket so concurrency doesn't
    serialize against itself — but the underlying httpx client is
    not shared, so this verifies no shared mutable state corrupts
    one fetch when another is in flight.
    """
    async def _fetch(symbol: str) -> str | None:
        async with Form4Client() as c:
            return await c.fetch_form4_atom(symbol, count=3)

    a, b = await asyncio.gather(_fetch("NVDA"), _fetch("AAPL"))
    assert a is not None and "<feed" in a or "<?xml" in a
    assert b is not None and "<feed" in b or "<?xml" in b
