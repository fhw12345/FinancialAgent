"""
Build sector universe CSV for the Today's Picks flow.

One-time runner. Scrapes the S&P 500 + Nasdaq 100 constituent lists from
Wikipedia (free, public), then enriches each ticker with sector / industry /
market cap via yfinance.

Anti-scrape protections:
- Rotating browser UA on every Wikipedia + Yahoo request
- Random 0.3-0.8s sleep between yfinance calls
- Exponential backoff retry (3 attempts, 1s/2s/4s) per ticker
- Failure-tolerant: skipped tickers logged, partial CSV still written
- Output is committed to git so production never re-fetches at runtime

Run from inside the backend container:
    python scripts/build_sector_universe.py
"""

from __future__ import annotations

import csv
import logging
import random
import sys
import time
from pathlib import Path

import structlog

OUTPUT_PATH = Path("/app/data/sector_universe.csv")
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


def _ua() -> str:
    return random.choice(USER_AGENTS)


def _get_html(url: str) -> str:
    """Fetch a URL with rotating UA and basic retry."""
    import urllib.request

    last_err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _ua()})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            last_err = e
            wait = 2**attempt
            time.sleep(wait)
    raise RuntimeError(f"Failed to fetch {url} after 3 attempts: {last_err}")


def fetch_sp500_symbols() -> list[str]:
    """Scrape S&P 500 ticker list from Wikipedia."""
    import re

    html = _get_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    # Wikipedia table cell pattern: <td><a href="/wiki/...">SYMBOL</a></td>
    rows = re.findall(
        r'<td><a[^>]+rel="nofollow"[^>]*>([A-Z][A-Z0-9.\-]{0,5})</a>', html
    )
    if not rows:
        # Fallback: any 1-5 cap-letter token in <td>
        rows = re.findall(r"<td>([A-Z]{1,5}(?:\.[A-Z])?)</td>", html)
    out = sorted(set(s.replace(".", "-") for s in rows if 1 <= len(s) <= 6))
    return out


def fetch_nasdaq100_symbols() -> list[str]:
    """Scrape Nasdaq 100 ticker list from Wikipedia."""
    import re

    html = _get_html("https://en.wikipedia.org/wiki/Nasdaq-100")
    rows = re.findall(r"<td>([A-Z]{1,5}(?:\.[A-Z])?)</td>", html)
    out = sorted(set(s.replace(".", "-") for s in rows if 1 <= len(s) <= 6))
    return out


def enrich_one(symbol: str) -> dict | None:
    """Fetch yfinance Ticker.info; return dict or None on failure."""
    import yfinance as yf

    last_err = None
    for attempt in range(3):
        try:
            info = yf.Ticker(symbol).info
            sector = info.get("sector") or ""
            industry = info.get("industry") or ""
            name = info.get("longName") or info.get("shortName") or symbol
            mcap = info.get("marketCap") or 0
            if not sector or not industry:
                return None  # not a useful row
            return {
                "symbol": symbol,
                "name": name[:80],
                "sector": sector,
                "industry": industry,
                "market_cap_b": round(mcap / 1_000_000_000, 2) if mcap else 0.0,
            }
        except Exception as e:
            last_err = e
            time.sleep(2**attempt)
    structlog.get_logger().warning("enrich_failed", symbol=symbol, error=str(last_err))
    return None


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ]
    )
    log = structlog.get_logger("build_universe")

    sys.path.insert(0, "/app")

    log.info("fetch_sp500_start")
    try:
        sp = fetch_sp500_symbols()
    except Exception as e:
        log.error("sp500_fetch_failed", error=str(e))
        sp = []
    log.info("fetch_sp500_done", count=len(sp))

    log.info("fetch_ndx_start")
    try:
        ndx = fetch_nasdaq100_symbols()
    except Exception as e:
        log.error("ndx_fetch_failed", error=str(e))
        ndx = []
    log.info("fetch_ndx_done", count=len(ndx))

    universe = sorted(set(sp) | set(ndx))
    log.info("universe_assembled", count=len(universe))
    if not universe:
        log.error("empty_universe_abort")
        return 1

    rows: list[dict] = []
    for i, sym in enumerate(universe, 1):
        if i % 25 == 0:
            log.info("enrich_progress", done=i, total=len(universe))
        row = enrich_one(sym)
        if row is not None:
            rows.append(row)
        # Anti-scrape: random small jitter between calls
        time.sleep(random.uniform(0.3, 0.8))

    log.info("enrich_done", succeeded=len(rows), failed=len(universe) - len(rows))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["symbol", "name", "sector", "industry", "market_cap_b"]
        )
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: -r["market_cap_b"]))

    log.info("csv_written", path=str(OUTPUT_PATH), rows=len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
