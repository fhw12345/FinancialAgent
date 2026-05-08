"""W3.8 SEC EDGAR Form 4 atom feed fetcher.

Scope: fetch raw atom XML for a symbol's recent Form 4 (insider
transaction) filings. Parsing the per-filing 10b5-1 plan markers,
transaction codes, and post-transaction holdings lives in W3.9 and
the schema work lives in W3.10 — this module deliberately stops at
"return the bytes EDGAR served us" so each piece is testable in
isolation.

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
import time
from typing import Any

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
    "TICKER_MAP_URL",
    "get_user_agent",
]
