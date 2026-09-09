"""Safe SEC Form 4 parsers and public compatibility exports.

HTTP transport/rate limiting lives in form4_transport; XML rejects DTD/entities.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

import httpx
import structlog
from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from .form4_transport import (
    ATOM_FEED_URL,
    DEFAULT_RATE_LIMIT_PER_SEC,
    DEFAULT_USER_AGENT,
    TICKER_MAP_URL,
    Form4Client,
    get_user_agent,
)

logger = structlog.get_logger()


# Accept both namespaced and bare SEC ownership-document elements.
_LOCAL_NAME = re.compile(r"\{[^}]+\}")


def _strip_ns(tag: str) -> str:
    return _LOCAL_NAME.sub("", tag)


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
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
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
        root = SafeET.fromstring(atom_xml, forbid_dtd=True)
    except (ET.ParseError, DefusedXmlException):
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
        root = SafeET.fromstring(detail_xml, forbid_dtd=True)
    except (ET.ParseError, DefusedXmlException):
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
        code_el = (
            _walk_first(coding_el, "transactionCode") if coding_el is not None else None
        )
        tx_code = _xml_text(code_el)

        amounts_el = _walk_first(tx, "transactionAmounts")
        shares = None
        share_price = None
        if amounts_el is not None:
            shares = _parse_float(
                _xml_text(
                    _xml_value_child(_walk_first(amounts_el, "transactionShares"))
                )
            )
            share_price = _parse_float(
                _xml_text(
                    _xml_value_child(
                        _walk_first(amounts_el, "transactionPricePerShare")
                    )
                )
            )

        post_el = _walk_first(tx, "postTransactionAmounts")
        shares_after = None
        if post_el is not None:
            shares_after = _parse_float(
                _xml_text(
                    _xml_value_child(
                        _walk_first(post_el, "sharesOwnedFollowingTransaction")
                    )
                )
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
