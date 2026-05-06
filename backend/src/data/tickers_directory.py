"""Tickers-directory loader — wide-coverage search source.

Reads `backend/data/tickers_directory.csv` (~6800 actively listed US tickers
from Nasdaq Trader) at first call, caches in-process. Schema is intentionally
narrow (symbol, name, exchange) — no sector/market_cap. Used by the symbol
search endpoint as a coverage layer on top of the curated sector_universe.

The CSV is built by scripts/build_tickers_directory.py and refreshed
manually (Nasdaq Trader publishes daily; we don't auto-pull).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class TickerRow:
    symbol: str
    name: str
    exchange: str


_CSV_CANDIDATES = [
    Path("/app/data/tickers_directory.csv"),
    Path(__file__).resolve().parents[3] / "data" / "tickers_directory.csv",
]


def _resolve_path() -> Path | None:
    for p in _CSV_CANDIDATES:
        if p.exists():
            return p
    return None


@lru_cache(maxsize=1)
def load_directory() -> list[TickerRow]:
    """Read the directory once. Empty list (with warning) if file missing —
    the symbol search endpoint will still work on the smaller sector_universe
    plus the yfinance fallback."""
    path = _resolve_path()
    if path is None:
        logger.warning(
            "tickers_directory_missing",
            tried=[str(p) for p in _CSV_CANDIDATES],
            hint="run scripts/build_tickers_directory.py to generate it",
        )
        return []
    rows: list[TickerRow] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            sym = (r.get("symbol") or "").strip()
            if not sym:
                continue
            rows.append(
                TickerRow(
                    symbol=sym,
                    name=(r.get("name") or "").strip(),
                    exchange=(r.get("exchange") or "").strip(),
                )
            )
    logger.info("tickers_directory_loaded", count=len(rows), source=str(path))
    return rows
