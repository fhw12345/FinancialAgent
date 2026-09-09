"""SEC HTTP transport and rate limiter; public imports remain in form4.py."""

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
DEFAULT_RATE_LIMIT_PER_SEC = 8.0


def get_user_agent() -> str:
    """Honor the SEC contact override without rejecting an empty value."""
    raw = os.environ.get("SEC_EDGAR_USER_AGENT", "")
    raw = raw.strip()
    return raw or DEFAULT_USER_AGENT


class _TokenBucket:
    """One locked rate-limit bucket per client; shared across its requests."""

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
    """Reusable async SEC client with an injectable outer HTTP transport."""

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
            headers={
                "User-Agent": self._user_agent,
                "Accept": "application/atom+xml,application/xml,text/xml,*/*",
            },
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
        mapping = await self._ensure_ticker_map()
        cik = mapping.get(symbol.upper())
        if cik is None:
            logger.warning("sec_edgar_cik_lookup_miss", symbol=symbol)
        return cik

    async def fetch_form4_atom(self, symbol: str, count: int = 40) -> str | None:
        cik = await self.lookup_cik(symbol)
        if cik is None:
            return None
        count = max(1, min(int(count), 100))
        url = ATOM_FEED_URL.format(cik=cik, count=count)
        resp = await self._request(url)
        return resp.text
