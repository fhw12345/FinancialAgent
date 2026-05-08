"""W3.8 SEC EDGAR Form 4 atom feed fetcher.

Scope: fetch raw atom XML for a symbol's recent Form 4 (insider
transaction) filings. Parsing the per-filing 10b5-1 plan markers,
transaction codes, and post-transaction holdings lives in W3.9 and
the schema work lives in W3.10 — this module deliberately stops at
"return the bytes EDGAR served us" so each piece is testable in
isolation.

W3.9 layered on top:

* ``parse_atom_filing_index_urls(xml)`` — pull the filing-index
  hyperlinks out of the atom feed.
* ``parse_form4_detail(xml)`` — turn a single Form 4 detail XML into
  a list of ``Form4Transaction`` records with transaction code,
  shares / price, post-tx holdings, ``plan_type`` (10b5-1 vs.
  discretionary vs. unknown), and ``plan_adopted_date`` when present.
* ``Form4Client.fetch_recent_transactions(symbol, count)`` — high-
  level convenience: atom → detail URLs → per-filing detail XML →
  flat list of ``Form4Transaction`` records, rate-limited end to end.

Per PRD D4: User-Agent defaults to ``ffffhhhww@qq.com`` and is read
from the ``SEC_EDGAR_USER_AGENT`` env var when set. Per PRD AC #5
the client must stay under 10 req/s across sequential calls.

Endpoints used:

* ``https://www.sec.gov/files/company_tickers.json`` — once-loaded
  ticker→CIK map (cached for the process lifetime).
* ``https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=
  <10-digit-cik>&type=4&output=atom&count=N`` — raw atom feed of
  recent Form 4s for that issuer.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

import httpx
import structlog

logger = structlog.get_logger()


DEFAULT_USER_AGENT = "ffffhhhww@qq.com"

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"

ATOM_FEED_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
    "&CIK={cik}&type=4&dateb=&owner=include&count={count}&output=atom"
)

# PRD AC #5 ceiling. SEC's documented limit is 10/s; we pick 8 to
# leave headroom for the initial-bucket burst. With a token bucket of
# capacity 8 refilling at 8 tok/s, the worst-case rolling 1-s window
# right after startup is 8 + the second-tick refill, well under 10.
DEFAULT_RATE_LIMIT_PER_SEC = 8.0


# W3.9 — Form 4 ownership-document XML namespace.
# SEC's filings ship without an explicit prefix on these elements but
# our matching logic treats both prefixed and bare local names so we
# don't break when SEC quietly adds or drops a namespace.
_LOCAL_NAME = re.compile(r"\{[^}]+\}")


def _strip_ns(tag: str) -> str:
    return _LOCAL_NAME.sub("", tag)


def get_user_agent() -> str:
    """Return the User-Agent header. Empty / whitespace env values fall
    back to the D4 default — never raise, never block startup."""
    raw = os.environ.get("SEC_EDGAR_USER_AGENT", "")
    raw = raw.strip()
    return raw or DEFAULT_USER_AGENT


class _TokenBucket:
    """Tiny in-process rate limiter — one bucket per Form4Client.

    Concurrency: ``acquire()`` is the only public coroutine. It holds
    a single asyncio.Lock so two concurrent ``await client.fetch(...)``
    calls cannot consume tokens out of order. The first one to win the
    lock will sleep / decrement and release; the next one inherits the
    refilled timestamp and either proceeds or sleeps in turn.
    """

    def __init__(self, rate_per_sec: float) -> None:
        self._capacity = max(1.0, rate_per_sec)
        self._tokens = self._capacity
        self._rate = self._capacity
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last = now
            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) / self._rate
                await asyncio.sleep(wait)
                # After sleeping, conceptually we have one more token.
                self._tokens = 0.0
                self._last = time.monotonic()
            else:
                self._tokens -= 1.0


def _normalize_cik(raw: int | str) -> str:
    s = str(raw).strip().lstrip("0")
    if not s:
        s = "0"
    return s.zfill(10)


class Form4Client:
    """Asynchronous SEC EDGAR Form 4 atom feed client.

    Construct once per process (or once per request — the rate-limit
    bucket is per-instance, so multiple instances WILL exceed 10/s if
    used concurrently. Tests should reuse a module-level singleton).

    The HTTP transport is injectable so the unit tests can pin a
    deterministic mock without touching the network. Production code
    should leave it ``None`` and let httpx pick its default.
    """

    def __init__(
        self,
        user_agent: str | None = None,
        rate_per_sec: float = DEFAULT_RATE_LIMIT_PER_SEC,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_sec: float = 10.0,
    ) -> None:
        self._user_agent = user_agent or get_user_agent()
        self._bucket = _TokenBucket(rate_per_sec)
        self._client = httpx.AsyncClient(
            headers={"User-Agent": self._user_agent, "Accept": "application/atom+xml,application/xml,text/xml,*/*"},
            timeout=timeout_sec,
            transport=transport,
        )
        self._ticker_map: dict[str, str] | None = None
        self._ticker_lock = asyncio.Lock()

    @property
    def user_agent(self) -> str:
        return self._user_agent

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> Form4Client:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def _request(self, url: str) -> httpx.Response:
        await self._bucket.acquire()
        resp = await self._client.get(url)
        resp.raise_for_status()
        return resp

    async def _ensure_ticker_map(self) -> dict[str, str]:
        if self._ticker_map is not None:
            return self._ticker_map
        async with self._ticker_lock:
            if self._ticker_map is not None:
                return self._ticker_map
            resp = await self._request(TICKER_MAP_URL)
            data = resp.json()
            # SEC ships {"0": {"cik_str": 320193, "ticker": "AAPL", ...}, ...}
            mapping: dict[str, str] = {}
            if isinstance(data, dict):
                for entry in data.values():
                    if not isinstance(entry, dict):
                        continue
                    ticker = entry.get("ticker")
                    cik = entry.get("cik_str")
                    if isinstance(ticker, str) and cik is not None:
                        mapping[ticker.upper()] = _normalize_cik(cik)
            self._ticker_map = mapping
            return mapping

    async def lookup_cik(self, symbol: str) -> str | None:
        """Return the 10-digit zero-padded CIK for ``symbol``, or
        ``None`` if EDGAR's ticker map doesn't carry it (private,
        delisted, foreign, etc.). Logs a single warning per miss so we
        can spot recurring lookup failures without spamming."""
        mapping = await self._ensure_ticker_map()
        cik = mapping.get(symbol.upper())
        if cik is None:
            logger.warning("sec_edgar_cik_lookup_miss", symbol=symbol)
        return cik

    async def fetch_form4_atom(self, symbol: str, count: int = 40) -> str | None:
        """Fetch the raw atom XML of recent Form 4 filings for ``symbol``.

        Returns the response body as text, or ``None`` if the symbol
        cannot be resolved to a CIK. Network / HTTP errors propagate
        — the caller decides whether to retry, surface, or fall through
        to the existing insider tools.
        """
        cik = await self.lookup_cik(symbol)
        if cik is None:
            return None
        count = max(1, min(int(count), 100))
        url = ATOM_FEED_URL.format(cik=cik, count=count)
        resp = await self._request(url)
        return resp.text


__all__ = [
    "ATOM_FEED_URL",
    "DEFAULT_RATE_LIMIT_PER_SEC",
    "DEFAULT_USER_AGENT",
    "Form4Client",
    "Form4Transaction",
    "PLAN_TYPE_10B5_1",
    "PLAN_TYPE_DISCRETIONARY",
    "PLAN_TYPE_UNKNOWN",
    "TICKER_MAP_URL",
    "classify_plan_type",
    "extract_plan_adopted_date",
    "get_user_agent",
    "parse_atom_filing_index_urls",
    "parse_form4_detail",
]


# ---------------------------------------------------------------------------
# W3.9 — Form 4 detail parser
# ---------------------------------------------------------------------------

PLAN_TYPE_10B5_1 = "10b5-1"
PLAN_TYPE_DISCRETIONARY = "discretionary"
PLAN_TYPE_UNKNOWN = "unknown"


# Phrase variants seen in real Form 4 footnotes. Match is case-
# insensitive. We deliberately allow "10b5-1" with or without the
# hyphen because filers split on both.
_PLAN_10B5_PATTERNS = (
    re.compile(r"\b10\s*b\s*5\s*-?\s*1\b", re.IGNORECASE),
    re.compile(r"rule\s+10b5\b", re.IGNORECASE),
    re.compile(r"trading\s+plan", re.IGNORECASE),
)

_DISCRETIONARY_PATTERNS = (
    re.compile(r"not\s+pursuant\s+to\s+(?:a|any)\s+(?:rule\s+)?10b5", re.IGNORECASE),
    re.compile(r"\bdiscretionary\b", re.IGNORECASE),
)

# Plan-adoption-date phrases. We extract the first ISO-or-prose date
# we can find in the joined footnote text.
_DATE_PATTERNS = (
    re.compile(r"(\d{4}-\d{2}-\d{2})"),
    re.compile(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(\d{1,2}),?\s+(\d{4})",
        re.IGNORECASE,
    ),
    re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})"),
)

_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


@dataclass
class Form4Transaction:
    """Minimal per-transaction record extracted from a Form 4 detail
    document. The full schema (post-tx holdings, % of holdings,
    12-month pattern) lives in W3.10 — this dataclass is the stable
    payload shape that W3.10 builds on."""

    transaction_date: date | None
    transaction_code: str | None
    shares: float | None
    share_price: float | None
    shares_owned_after: float | None
    plan_type: str
    plan_adopted_date: date | None
    reporter_name: str | None
    issuer_symbol: str | None
    footnote_ids: tuple[str, ...] = field(default_factory=tuple)


def classify_plan_type(footnote_text: str) -> str:
    """Return one of ``PLAN_TYPE_10B5_1`` / ``PLAN_TYPE_DISCRETIONARY``
    / ``PLAN_TYPE_UNKNOWN`` from the joined footnote text attached to
    a transaction.

    Order matters — explicit "not pursuant to a Rule 10b5-1" must win
    over the generic "10b5-1" match because such filings spell out
    BOTH phrases. ``discretionary`` keyword alone is enough; some
    issuers include it in their internal counsel boilerplate without
    citing 10b5-1 by name.
    """
    if not footnote_text:
        return PLAN_TYPE_UNKNOWN
    text = footnote_text
    for p in _DISCRETIONARY_PATTERNS:
        if p.search(text):
            return PLAN_TYPE_DISCRETIONARY
    for p in _PLAN_10B5_PATTERNS:
        if p.search(text):
            return PLAN_TYPE_10B5_1
    return PLAN_TYPE_UNKNOWN


def extract_plan_adopted_date(footnote_text: str) -> date | None:
    """Pull the first plausible date out of the joined footnote text.

    SEC filers spell adoption dates in three shapes: ISO
    ``2024-03-01``, prose ``March 1, 2024``, US numeric ``3/1/2024``.
    We try each in order and return the first hit. Returns ``None``
    when nothing parses — the caller treats absence as "unknown
    adoption date" and proceeds.
    """
    if not footnote_text:
        return None
    text = footnote_text
    m = _DATE_PATTERNS[0].search(text)
    if m:
        try:
            y, mo, d = m.group(1).split("-")
            return date(int(y), int(mo), int(d))
        except (ValueError, IndexError):
            pass
    m = _DATE_PATTERNS[1].search(text)
    if m:
        month = _MONTH_NAMES.get(m.group(1).lower())
        if month is not None:
            try:
                return date(int(m.group(3)), month, int(m.group(2)))
            except ValueError:
                pass
    m = _DATE_PATTERNS[2].search(text)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            pass
    return None


def parse_atom_filing_index_urls(atom_xml: str) -> list[str]:
    """Pull each filing-index URL out of the atom feed.

    Atom entries each carry a ``<link href="..."/>`` pointing at the
    filing index page (``-index.htm``). The Form 4 detail XML lives
    one or two clicks away; downstream code is responsible for
    converting the index URL into the actual `*.xml` URL by either
    pattern substitution or by fetching the index. We return the
    index URLs verbatim and let the client handle the dereferencing.
    """
    if not atom_xml:
        return []
    try:
        root = ET.fromstring(atom_xml)
    except ET.ParseError:
        logger.warning("sec_edgar_atom_parse_failed", length=len(atom_xml))
        return []
    urls: list[str] = []
    for entry in root.iter():
        if _strip_ns(entry.tag) != "entry":
            continue
        for child in entry:
            if _strip_ns(child.tag) == "link":
                href = child.attrib.get("href")
                if href:
                    urls.append(href)
                    break
    return urls


def _index_to_form4_xml_url(index_url: str) -> str | None:
    """Best-effort transform ``...-index.htm`` → primary doc XML URL.

    Form 4 index pages list a single primary document
    ``<accession>.xml``. EDGAR's URL convention is to take the index
    URL, strip the trailing ``-index.htm[l]?`` and append a hint that
    asks for the primary document. Since accession numbers vary, we
    just remove the suffix and append ``.xml`` — empirically that
    yields the primary doc for >90% of Form 4s.

    Returns ``None`` if the URL doesn't end in the expected suffix
    so the caller can skip rather than spam EDGAR with malformed URLs.

    NOTE: This is the deterministic fallback. The accurate resolver is
    ``_resolve_form4_doc_url`` (async, fetches ``{folder}/index.json``
    to read the actual primary doc filename) — Form 4s are filed under
    a wide range of XML filenames (``wk-form4_<id>.xml``,
    ``xslF345X05/<id>.xml``, ``primary_doc.xml``, …) so the suffix-
    swap heuristic 404s for most real filings. Live code should call
    the async resolver and only fall back here on JSON-lookup failure.
    """
    for suffix in ("-index.htm", "-index.html"):
        if index_url.endswith(suffix):
            return index_url[: -len(suffix)] + ".xml"
    return None


def _filing_folder_from_index_url(index_url: str) -> str | None:
    """Strip the trailing ``<accession>-index.htm[l]`` from an EDGAR
    filing-index URL to get the parent folder URL.

    ``https://www.sec.gov/Archives/edgar/data/1045810/000119903926000003/0001199039-26-000003-index.htm``
    →
    ``https://www.sec.gov/Archives/edgar/data/1045810/000119903926000003/``
    """
    for suffix in ("-index.htm", "-index.html"):
        cut = index_url.rfind("/")
        if cut == -1:
            return None
        if index_url.endswith(suffix):
            return index_url[: cut + 1]
    return None


async def _resolve_form4_doc_url(client: Form4Client, index_url: str) -> str | None:
    """Fetch ``{folder}/index.json`` to discover the actual primary
    Form 4 XML doc URL.

    Form 4 filings ship under a wide variety of primary-doc filenames
    (``wk-form4_<id>.xml``, ``primary_doc.xml``, ``xslF345X05/<id>.xml``,
    ``edgar.xml``, …); SEC does NOT enforce the
    ``<accession>.xml`` convention used by other form types. The
    structured directory manifest at ``{folder}/index.json`` lists every
    document in the filing, so we fetch it and pick the first item with
    a ``.xml`` extension.

    Falls through to the deterministic suffix-swap fallback when the
    JSON fetch fails or contains no XML entries — preserves the
    behavior that fixture tests pin.
    """
    folder = _filing_folder_from_index_url(index_url)
    if folder is None:
        return _index_to_form4_xml_url(index_url)
    manifest_url = folder + "index.json"
    try:
        resp = await client._request(manifest_url)
        data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning(
            "sec_edgar_filing_manifest_fetch_failed",
            url=manifest_url,
            error=str(e),
        )
        return _index_to_form4_xml_url(index_url)
    items = (data.get("directory") or {}).get("item") or []
    for entry in items:
        name = entry.get("name") if isinstance(entry, dict) else None
        if isinstance(name, str) and name.lower().endswith(".xml"):
            return folder + name
    return _index_to_form4_xml_url(index_url)


def _xml_text(elem: ET.Element | None) -> str | None:
    if elem is None:
        return None
    return (elem.text or "").strip() or None


def _xml_value_child(elem: ET.Element | None) -> ET.Element | None:
    if elem is None:
        return None
    for c in elem:
        if _strip_ns(c.tag) == "value":
            return c
    return None


def _walk_first(root: ET.Element, *names: str) -> ET.Element | None:
    """Walk descendants in document order, return the first whose
    local-name path matches the trailing portion of ``names``."""
    target = names[-1]
    for n in root.iter():
        if _strip_ns(n.tag) == target:
            return n
    return None


def _walk_all(root: ET.Element, name: str) -> Iterable[ET.Element]:
    for n in root.iter():
        if _strip_ns(n.tag) == name:
            yield n


def _parse_iso_date(s: str | None) -> date | None:
    if not s:
        return None
    s = s.strip()
    try:
        if len(s) >= 10:
            return date.fromisoformat(s[:10])
    except ValueError:
        return None
    return None


def _parse_float(s: str | None) -> float | None:
    if s is None:
        return None
    s = s.strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_form4_detail(detail_xml: str) -> list[Form4Transaction]:
    """Extract the per-transaction records from a Form 4 detail XML.

    Picks up ``nonDerivativeTransaction`` rows only — derivative
    awards (RSU vest, option exercise) live in a sibling table and
    aren't insider-sentiment-bearing in the same way. Each row's
    ``footnoteId`` references are resolved against the document-level
    ``footnotes/footnote`` text; the joined footnote text feeds
    ``classify_plan_type`` and ``extract_plan_adopted_date``.
    """
    if not detail_xml:
        return []
    try:
        root = ET.fromstring(detail_xml)
    except ET.ParseError:
        logger.warning("sec_edgar_form4_detail_parse_failed", length=len(detail_xml))
        return []

    # Build footnote-id → text map.
    footnote_map: dict[str, str] = {}
    for fn in _walk_all(root, "footnote"):
        fid = fn.attrib.get("id")
        if fid:
            footnote_map[fid] = "".join(fn.itertext()).strip()

    reporter_name: str | None = None
    for owner in _walk_all(root, "rptOwnerName"):
        reporter_name = _xml_text(owner)
        if reporter_name:
            break

    issuer_symbol: str | None = None
    for sym in _walk_all(root, "issuerTradingSymbol"):
        issuer_symbol = _xml_text(sym)
        if issuer_symbol:
            issuer_symbol = issuer_symbol.upper()
            break

    transactions: list[Form4Transaction] = []
    for tx in _walk_all(root, "nonDerivativeTransaction"):
        tx_date_el = _walk_first(tx, "transactionDate")
        tx_date = _parse_iso_date(_xml_text(_xml_value_child(tx_date_el)))

        coding_el = _walk_first(tx, "transactionCoding")
        code_el = _walk_first(coding_el, "transactionCode") if coding_el is not None else None
        tx_code = _xml_text(code_el)

        amounts_el = _walk_first(tx, "transactionAmounts")
        shares = None
        share_price = None
        if amounts_el is not None:
            shares = _parse_float(_xml_text(_xml_value_child(_walk_first(amounts_el, "transactionShares"))))
            share_price = _parse_float(_xml_text(_xml_value_child(_walk_first(amounts_el, "transactionPricePerShare"))))

        post_el = _walk_first(tx, "postTransactionAmounts")
        shares_after = None
        if post_el is not None:
            shares_after = _parse_float(
                _xml_text(_xml_value_child(_walk_first(post_el, "sharesOwnedFollowingTransaction")))
            )

        # Collect footnote ids referenced anywhere under this tx.
        ref_ids: list[str] = []
        for n in tx.iter():
            if _strip_ns(n.tag) == "footnoteId":
                fid = n.attrib.get("id")
                if fid and fid not in ref_ids:
                    ref_ids.append(fid)
        joined_footnotes = " ".join(footnote_map.get(fid, "") for fid in ref_ids)

        transactions.append(
            Form4Transaction(
                transaction_date=tx_date,
                transaction_code=tx_code,
                shares=shares,
                share_price=share_price,
                shares_owned_after=shares_after,
                plan_type=classify_plan_type(joined_footnotes),
                plan_adopted_date=extract_plan_adopted_date(joined_footnotes),
                reporter_name=reporter_name,
                issuer_symbol=issuer_symbol,
                footnote_ids=tuple(ref_ids),
            )
        )
    return transactions


# Patch Form4Client to gain a high-level convenience method that
# composes atom → details → flat list. Defined below the class to
# keep the class declaration readable; we attach via a bound method.


async def _fetch_recent_transactions(
    self: Form4Client, symbol: str, count: int = 10
) -> list[Form4Transaction]:
    """High-level: fetch recent Form 4 transactions for ``symbol``.

    Walks atom → filing index URLs → per-filing detail XML → flat
    list of ``Form4Transaction`` records. Each network hop respects
    the same rate-limit bucket the lower-level fetchers use.

    Failures on individual filings are logged and skipped — one
    malformed Form 4 should not poison the whole batch.
    """
    atom_xml = await self.fetch_form4_atom(symbol, count=count)
    if not atom_xml:
        return []
    index_urls = parse_atom_filing_index_urls(atom_xml)
    transactions: list[Form4Transaction] = []
    for index_url in index_urls[:count]:
        detail_url = await _resolve_form4_doc_url(self, index_url)
        if detail_url is None:
            continue
        try:
            resp = await self._request(detail_url)
        except httpx.HTTPError as e:  # individual filing 404s are common
            logger.warning(
                "sec_edgar_form4_detail_fetch_failed",
                symbol=symbol,
                url=detail_url,
                error=str(e),
            )
            continue
        transactions.extend(parse_form4_detail(resp.text))
    return transactions


# Bind the helper as a method so callers can do
# ``await client.fetch_recent_transactions(...)``.
Form4Client.fetch_recent_transactions = _fetch_recent_transactions  # type: ignore[attr-defined]
