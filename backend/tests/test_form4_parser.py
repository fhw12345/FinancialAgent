"""W3.9 unit tests — Form 4 detail parser.

Coverage:

* ``classify_plan_type`` distinguishes 10b5-1 vs discretionary vs
  unknown across the phrasing variants real Form 4 filers use.
* ``extract_plan_adopted_date`` parses ISO / prose / US-numeric
  shapes and returns ``None`` on garbage.
* ``parse_atom_filing_index_urls`` pulls the per-entry ``link/href``
  out of a multi-entry atom feed and ignores entries without links.
* ``parse_form4_detail`` walks the SEC ownership-document XML to
  produce ``Form4Transaction`` rows: transaction date / code /
  shares / price / post-transaction holdings / plan_type +
  plan_adopted_date sourced from referenced footnotes / reporter
  name + issuer symbol.
* ``Form4Client.fetch_recent_transactions`` chains atom → detail →
  list end-to-end against a fully-mocked transport.

The parser is regex/XML-only — no SEC traffic.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from src.agent.tools.sec_edgar.form4 import (
    PLAN_TYPE_10B5_1,
    PLAN_TYPE_DISCRETIONARY,
    PLAN_TYPE_UNKNOWN,
    Form4Client,
    TICKER_MAP_URL,
    classify_plan_type,
    extract_plan_adopted_date,
    parse_atom_filing_index_urls,
    parse_form4_detail,
)


# ---------------------------------------------------------------------------
# classify_plan_type
# ---------------------------------------------------------------------------


def test_classify_plan_type_recognizes_canonical_10b5_1_phrasing() -> None:
    assert classify_plan_type(
        "Sale executed under a Rule 10b5-1 plan adopted on March 1, 2024."
    ) == PLAN_TYPE_10B5_1


def test_classify_plan_type_handles_unhyphenated_10b5_1() -> None:
    assert classify_plan_type(
        "Pursuant to a Rule 10b5 1 trading plan dated 2024-03-01."
    ) == PLAN_TYPE_10B5_1


def test_classify_plan_type_explicit_discretionary_overrides_10b5() -> None:
    """Real filings sometimes spell out BOTH phrases ('not pursuant
    to a Rule 10b5-1') and the discretionary signal must win."""
    assert classify_plan_type(
        "This transaction was not pursuant to a Rule 10b5-1 trading plan."
    ) == PLAN_TYPE_DISCRETIONARY


def test_classify_plan_type_recognizes_bare_discretionary() -> None:
    assert classify_plan_type(
        "Sale executed at the reporting person's discretionary direction."
    ) == PLAN_TYPE_DISCRETIONARY


def test_classify_plan_type_returns_unknown_when_text_is_silent() -> None:
    assert classify_plan_type("Bona fide gift to a charitable trust.") == PLAN_TYPE_UNKNOWN
    assert classify_plan_type("") == PLAN_TYPE_UNKNOWN
    assert classify_plan_type("    ") == PLAN_TYPE_UNKNOWN


# ---------------------------------------------------------------------------
# extract_plan_adopted_date
# ---------------------------------------------------------------------------


def test_extract_plan_adopted_date_iso_form() -> None:
    assert extract_plan_adopted_date(
        "10b5-1 plan adopted 2024-03-01."
    ) == date(2024, 3, 1)


def test_extract_plan_adopted_date_prose_form() -> None:
    assert extract_plan_adopted_date(
        "Plan adopted on March 1, 2024 by the reporting person."
    ) == date(2024, 3, 1)
    # Day without comma is also valid shape.
    assert extract_plan_adopted_date(
        "Adopted September 12 2025"
    ) == date(2025, 9, 12)


def test_extract_plan_adopted_date_us_numeric_form() -> None:
    assert extract_plan_adopted_date(
        "Plan dated 3/1/2024 governs all sales for Q1."
    ) == date(2024, 3, 1)


def test_extract_plan_adopted_date_returns_none_on_no_date() -> None:
    assert extract_plan_adopted_date("Sale of common stock.") is None
    assert extract_plan_adopted_date("") is None


# ---------------------------------------------------------------------------
# parse_atom_filing_index_urls
# ---------------------------------------------------------------------------


_ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Form 4 — Apple Inc.</title>
  <entry>
    <title>4 - Cook Timothy D</title>
    <link href="https://www.sec.gov/Archives/edgar/data/320193/000032019326000123/0000320193-26-000123-index.htm"/>
    <updated>2026-05-07T16:00:00-04:00</updated>
  </entry>
  <entry>
    <title>4 - Maestri Luca</title>
    <link href="https://www.sec.gov/Archives/edgar/data/320193/000032019326000124/0000320193-26-000124-index.htm"/>
    <updated>2026-05-06T16:00:00-04:00</updated>
  </entry>
  <entry>
    <title>4 - No Link Here</title>
    <updated>2026-05-05T16:00:00-04:00</updated>
  </entry>
</feed>
"""


def test_parse_atom_filing_index_urls_extracts_per_entry_links() -> None:
    urls = parse_atom_filing_index_urls(_ATOM_FEED)
    assert len(urls) == 2  # third entry has no link, skipped
    assert all("index.htm" in u for u in urls)
    assert urls[0].endswith("0000320193-26-000123-index.htm")
    assert urls[1].endswith("0000320193-26-000124-index.htm")


def test_parse_atom_filing_index_urls_returns_empty_on_garbage() -> None:
    assert parse_atom_filing_index_urls("") == []
    assert parse_atom_filing_index_urls("not xml at all") == []


# ---------------------------------------------------------------------------
# parse_form4_detail
# ---------------------------------------------------------------------------


_FORM4_DETAIL_10B5_1 = """<?xml version="1.0" encoding="UTF-8"?>
<ownershipDocument>
  <issuer>
    <issuerCik>0000320193</issuerCik>
    <issuerName>Apple Inc.</issuerName>
    <issuerTradingSymbol>aapl</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerName>Cook Timothy D</rptOwnerName>
    </reportingOwnerId>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>2026-05-07</value></transactionDate>
      <transactionCoding>
        <transactionCode>S</transactionCode>
      </transactionCoding>
      <transactionAmounts>
        <transactionShares><value>10000</value></transactionShares>
        <transactionPricePerShare><value>185.42</value></transactionPricePerShare>
      </transactionAmounts>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>3247500</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
      <transactionCoding>
        <footnoteId id="F1"/>
      </transactionCoding>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>2026-05-07</value></transactionDate>
      <transactionCoding>
        <transactionCode>S</transactionCode>
      </transactionCoding>
      <transactionAmounts>
        <transactionShares><value>5000</value></transactionShares>
        <transactionPricePerShare><value>185.81</value></transactionPricePerShare>
      </transactionAmounts>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>3242500</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
      <footnoteId id="F1"/>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
  <footnotes>
    <footnote id="F1">Sale executed pursuant to a Rule 10b5-1 trading plan adopted on March 1, 2024.</footnote>
  </footnotes>
</ownershipDocument>
"""


def test_parse_form4_detail_extracts_two_10b5_1_transactions() -> None:
    txs = parse_form4_detail(_FORM4_DETAIL_10B5_1)
    assert len(txs) == 2
    a, b = txs
    assert a.transaction_date == date(2026, 5, 7)
    assert a.transaction_code == "S"
    assert a.shares == 10000.0
    assert a.share_price == 185.42
    assert a.shares_owned_after == 3247500.0
    assert a.plan_type == PLAN_TYPE_10B5_1
    assert a.plan_adopted_date == date(2024, 3, 1)
    assert a.reporter_name == "Cook Timothy D"
    assert a.issuer_symbol == "AAPL"  # uppercased
    assert a.footnote_ids == ("F1",)
    # Second tx still resolves the footnote even though its
    # footnoteId reference sits at a different XML depth.
    assert b.plan_type == PLAN_TYPE_10B5_1
    assert b.plan_adopted_date == date(2024, 3, 1)


_FORM4_DETAIL_DISCRETIONARY = """<?xml version="1.0" encoding="UTF-8"?>
<ownershipDocument>
  <issuer><issuerTradingSymbol>NVDA</issuerTradingSymbol></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Huang Jen-Hsun</rptOwnerName></reportingOwnerId>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-05-08</value></transactionDate>
      <transactionCoding>
        <transactionCode>S</transactionCode>
        <footnoteId id="F1"/>
      </transactionCoding>
      <transactionAmounts>
        <transactionShares><value>120000</value></transactionShares>
        <transactionPricePerShare><value>955.30</value></transactionPricePerShare>
      </transactionAmounts>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>800000</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
  <footnotes>
    <footnote id="F1">This transaction was not pursuant to a Rule 10b5-1 trading plan; it reflects the reporting person's discretionary direction.</footnote>
  </footnotes>
</ownershipDocument>
"""


def test_parse_form4_detail_classifies_explicit_discretionary() -> None:
    txs = parse_form4_detail(_FORM4_DETAIL_DISCRETIONARY)
    assert len(txs) == 1
    assert txs[0].plan_type == PLAN_TYPE_DISCRETIONARY
    assert txs[0].plan_adopted_date is None
    assert txs[0].reporter_name == "Huang Jen-Hsun"
    assert txs[0].issuer_symbol == "NVDA"


_FORM4_DETAIL_NO_FOOTNOTES = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer><issuerTradingSymbol>TSLA</issuerTradingSymbol></issuer>
  <reportingOwner><reportingOwnerId><rptOwnerName>Musk Elon</rptOwnerName></reportingOwnerId></reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-05-09</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1500</value></transactionShares>
        <transactionPricePerShare><value>312.10</value></transactionPricePerShare>
      </transactionAmounts>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>411500</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
"""


def test_parse_form4_detail_no_footnotes_yields_unknown_plan_type() -> None:
    txs = parse_form4_detail(_FORM4_DETAIL_NO_FOOTNOTES)
    assert len(txs) == 1
    assert txs[0].transaction_code == "P"
    assert txs[0].plan_type == PLAN_TYPE_UNKNOWN
    assert txs[0].plan_adopted_date is None


def test_parse_form4_detail_returns_empty_on_garbage() -> None:
    assert parse_form4_detail("") == []
    assert parse_form4_detail("not xml at all") == []
    # Valid XML but wrong shape — no nonDerivativeTransaction nodes.
    assert parse_form4_detail("<root><x/></root>") == []


# ---------------------------------------------------------------------------
# Form4Client.fetch_recent_transactions (end-to-end against MockTransport)
# ---------------------------------------------------------------------------


_TICKER_MAP_BODY = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
}


def _build_handler():
    """Mock SEC: ticker map, atom feed, two filing-detail XMLs."""

    detail_a = _FORM4_DETAIL_10B5_1
    detail_b = _FORM4_DETAIL_DISCRETIONARY.replace("NVDA", "AAPL")  # 2nd filing for AAPL

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == TICKER_MAP_URL:
            return httpx.Response(200, json=_TICKER_MAP_BODY)
        if "browse-edgar" in url:
            return httpx.Response(200, text=_ATOM_FEED, headers={"Content-Type": "application/atom+xml"})
        if url.endswith("0000320193-26-000123.xml"):
            return httpx.Response(200, text=detail_a, headers={"Content-Type": "application/xml"})
        if url.endswith("0000320193-26-000124.xml"):
            return httpx.Response(200, text=detail_b, headers={"Content-Type": "application/xml"})
        return httpx.Response(404, text="not mocked")

    return handler


@pytest.mark.asyncio
async def test_fetch_recent_transactions_chains_atom_to_details() -> None:
    transport = httpx.MockTransport(_build_handler())
    async with Form4Client(transport=transport, rate_per_sec=1000.0) as client:
        txs = await client.fetch_recent_transactions("AAPL", count=10)
    # First filing has 2 nonDerivative tx, second has 1 → 3 total.
    assert len(txs) == 3
    plans = [t.plan_type for t in txs]
    # 10b5-1 from filing A (×2) + discretionary from filing B (×1)
    assert plans.count(PLAN_TYPE_10B5_1) == 2
    assert plans.count(PLAN_TYPE_DISCRETIONARY) == 1
    # PRD AC #3: plan_type populated for ≥3 of N transactions.
    assert sum(1 for t in txs if t.plan_type != PLAN_TYPE_UNKNOWN) >= 3


@pytest.mark.asyncio
async def test_fetch_recent_transactions_skips_individual_failures() -> None:
    """A single 404 on one detail URL must not blow up the whole batch."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == TICKER_MAP_URL:
            return httpx.Response(200, json=_TICKER_MAP_BODY)
        if "browse-edgar" in url:
            return httpx.Response(200, text=_ATOM_FEED)
        if url.endswith("0000320193-26-000123.xml"):
            return httpx.Response(200, text=_FORM4_DETAIL_10B5_1)
        if url.endswith("0000320193-26-000124.xml"):
            return httpx.Response(404, text="missing")
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with Form4Client(transport=transport, rate_per_sec=1000.0) as client:
        txs = await client.fetch_recent_transactions("AAPL", count=10)
    # Only the first filing (2 tx) survives.
    assert len(txs) == 2
    assert all(t.plan_type == PLAN_TYPE_10B5_1 for t in txs)


@pytest.mark.asyncio
async def test_fetch_recent_transactions_returns_empty_for_unknown_symbol() -> None:
    transport = httpx.MockTransport(_build_handler())
    async with Form4Client(transport=transport, rate_per_sec=1000.0) as client:
        txs = await client.fetch_recent_transactions("UNKNOWN_TICKER_XYZ")
    assert txs == []
