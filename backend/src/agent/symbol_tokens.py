"""Shared deterministic parsing for explicit stock ticker tokens."""

from __future__ import annotations

import re

_SYMBOL_PATTERN = re.compile(r"\b([A-Z]{1,5}(?:[.-][A-Z])?)\b")
_VALID_SYMBOL_PATTERN = re.compile(r"^[A-Z]{1,5}(?:[.-][A-Z])?$")
_GENERIC_UPPERCASE_TOKENS = {
    "AI",
    "ALL",
    "AND",
    "ARE",
    "ASK",
    "BIG",
    "BUY",
    "CAN",
    "CEO",
    "CFO",
    "CPI",
    "DEEP",
    "DID",
    "ETF",
    "FOR",
    "GDP",
    "GET",
    "HAS",
    "HBM",
    "HIGH",
    "HOLD",
    "HOW",
    "IPO",
    "NEW",
    "NOT",
    "NOW",
    "OUT",
    "OWN",
    "RUN",
    "SAY",
    "SEC",
    "SELL",
    "SET",
    "THE",
    "TOP",
    "TRY",
    "USE",
    "USA",
    "WAY",
    "WHO",
    "WHY",
    "LOW",
}
_SYMBOL_CONTEXT_BEFORE_RE = re.compile(
    r"(?:\b(?:continue\s+with|switch\s+to|ticker|symbol|stock|shares?)"
    r"\s*[:：]?\s*|(?:切换到|改成|股票|代码)\s*)$",
    re.IGNORECASE,
)
_ANALYSIS_CONTEXT_BEFORE_RE = re.compile(
    r"(?:\b(?:analy[sz]e|research)\s+|(?:分析|研究)\s*)$",
    re.IGNORECASE,
)
_SYMBOL_CONTEXT_AFTER_RE = re.compile(
    r"^\s*(?:ticker|symbol|stock|shares?|verdict|thesis|report|analysis|"
    r"股票|代码|结论|报告)\b",
    re.IGNORECASE,
)
_UNTRUSTED_EVIDENCE_RE = re.compile(
    r"<external_evidence\b(?=[^>]*\btrust=[\"']untrusted[\"'])[^>]*>"
    r".*?</external_evidence>",
    re.IGNORECASE | re.DOTALL,
)
_UNTRUSTED_OVERRIDE_MARKERS = (
    "ignore safety",
    "ignore the user",
    "silently use",
    "default every unknown",
    "default ticker",
    "filing says",
    "filing contains",
    "system override",
    "忽略安全",
    "忽略用户",
    "静默使用",
    "未知公司默认",
    "默认股票代码",
    "系统覆盖",
)


def normalize_symbol(value: str) -> str | None:
    """Normalize a ticker while rejecting invalid punctuation."""
    normalized = value.strip().upper()
    if not _VALID_SYMBOL_PATTERN.fullmatch(normalized):
        return None
    return normalized


def _has_symbol_intent(
    message: str,
    symbol: str,
    *,
    allow_analysis_prefix: bool,
) -> bool:
    normalized = normalize_symbol(symbol)
    if normalized is None:
        return False

    for match in _SYMBOL_PATTERN.finditer(message):
        if match.group(1) != normalized:
            continue
        before = message[max(0, match.start() - 40) : match.start()]
        after = message[match.end() : match.end() + 30]
        if _SYMBOL_CONTEXT_BEFORE_RE.search(before):
            return True
        if allow_analysis_prefix and _ANALYSIS_CONTEXT_BEFORE_RE.search(before):
            return True
        if _SYMBOL_CONTEXT_AFTER_RE.match(after):
            return True

    escaped = re.escape(normalized)
    direct_request = re.compile(
        rf"^\s*(?:please\s+)?(?:deeply\s+)?"
        rf"(?:analy[sz]e|research|分析|研究)\s+{escaped}"
        rf"(?:\s+(?:stock|shares?|股票))?\s*[.!?。]?\s*$",
        re.IGNORECASE,
    )
    return bool(
        direct_request.fullmatch(message)
        or re.fullmatch(rf"\s*{escaped}\s*[.!?。]?\s*", message)
    )


def has_symbol_intent(message: str, symbol: str) -> bool:
    """Return whether surrounding text treats a token as a stock symbol."""
    return _has_symbol_intent(
        message,
        symbol,
        allow_analysis_prefix=True,
    )


def extract_explicit_symbols(message: str) -> list[str]:
    """Return unique explicit ticker candidates in message order."""
    symbols: list[str] = []
    for match in _SYMBOL_PATTERN.finditer(message):
        symbol = normalize_symbol(match.group(1))
        if symbol is None or symbol in symbols:
            continue
        if symbol in _GENERIC_UPPERCASE_TOKENS and not _has_symbol_intent(
            message,
            symbol,
            allow_analysis_prefix=False,
        ):
            continue
        symbols.append(symbol)
    return symbols


def strip_untrusted_evidence(message: str) -> str:
    """Remove explicitly tagged external evidence before resolving user intent."""
    return _UNTRUSTED_EVIDENCE_RE.sub(" ", message)


def is_untrusted_symbol_override(message: str, symbol: str) -> bool:
    """Detect a ticker that appears only inside an override-style instruction."""
    normalized = normalize_symbol(symbol)
    if normalized is None:
        return False
    occurrences = [
        match.start()
        for match in re.finditer(
            rf"(?<![A-Za-z0-9]){re.escape(normalized)}(?![A-Za-z0-9])",
            message,
            re.IGNORECASE,
        )
    ]
    if not occurrences:
        return False
    lowered = message.lower()
    return all(
        any(
            marker in lowered[max(0, index - 120) : index + 80]
            for marker in _UNTRUSTED_OVERRIDE_MARKERS
        )
        for index in occurrences
    )


def has_explicit_symbol_intent(
    message: str,
    symbols: list[str] | None = None,
) -> bool:
    """Return whether any candidate is presented as an intended ticker."""
    candidates = symbols or [
        match.group(1) for match in _SYMBOL_PATTERN.finditer(message)
    ]
    return any(has_symbol_intent(message, symbol) for symbol in candidates)
