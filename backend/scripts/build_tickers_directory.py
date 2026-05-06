"""Build backend/data/tickers_directory.csv from Nasdaq Trader.

Pulls the daily-published symbol directories from nasdaqtrader.com and
filters out non-equity / test / preferred / warrant / unit rows. Output
covers ~7000 actively listed US tickers (NYSE + NYSE American + NYSE Arca
+ Nasdaq + BATS) — the wide-net source for the symbol-search endpoint.

This is independent from sector_universe.csv, which is a smaller curated
list of 515 large-caps with sector/industry/market_cap data used by the
picks/portfolio analysis flows. Two files, two purposes:

  sector_universe.csv  → analytical use (sector rotation, market-cap filters)
  tickers_directory.csv → coverage for symbol search / autocomplete

Run:
  docker compose exec backend python scripts/build_tickers_directory.py
  # writes /app/data/tickers_directory.csv

Or from host (network needed):
  python backend/scripts/build_tickers_directory.py
  # writes backend/data/tickers_directory.csv
"""

from __future__ import annotations

import csv
import sys
import urllib.request
from pathlib import Path

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt"

# `otherlisted.txt` exchange code → human-readable label
_OTHER_EXCHANGES = {
    "A": "NYSE American",
    "N": "NYSE",
    "P": "NYSE Arca",
    "Z": "Cboe BZX",
    "V": "IEX",
}

# Junk-suffix patterns that indicate non-common-stock instruments. We exclude
# these to keep search results focused on tickers a retail user would buy.
_JUNK_SYMBOL_CHARS = ("$", ".", "=", "+", "^")


def _strip_corp_suffix(name: str) -> str:
    """Best-effort cleanup so 'Apple Inc. - Common Stock' shows as 'Apple Inc.'.
    nasdaqtrader names are verbose; the search UI just needs the company name."""
    s = name.strip()
    for suffix in (
        " - Common Stock",
        " - Class A Common Stock",
        " Common Stock",
        " Common Shares",
        " Ordinary Shares",
        " - Class A Ordinary Shares",
        " - American Depositary Shares",
        " American Depositary Shares",
    ):
        if s.endswith(suffix):
            return s[: -len(suffix)].strip()
    return s


def _fetch(url: str) -> list[str]:
    with urllib.request.urlopen(url, timeout=30) as r:  # noqa: S310 (trusted source)
        return r.read().decode("utf-8", errors="replace").splitlines()


def _parse_nasdaq_listed(lines: list[str]) -> list[tuple[str, str, str]]:
    """nasdaqlisted.txt fields: Symbol|Security Name|Market Category|Test Issue|
    Financial Status|Round Lot Size|ETF|NextShares
    Last line is a 'File Creation Time' footer — must skip.
    """
    out = []
    if not lines:
        return out
    header = lines[0].split("|")
    idx_sym = header.index("Symbol")
    idx_name = header.index("Security Name")
    idx_test = header.index("Test Issue")
    idx_etf = header.index("ETF")
    for line in lines[1:]:
        if not line or line.startswith("File Creation Time"):
            continue
        parts = line.split("|")
        if len(parts) < len(header):
            continue
        sym = parts[idx_sym].strip()
        if not sym or any(c in sym for c in _JUNK_SYMBOL_CHARS):
            continue
        if parts[idx_test] == "Y":
            continue
        if parts[idx_etf] == "Y":
            continue
        name = _strip_corp_suffix(parts[idx_name])
        out.append((sym, name, "Nasdaq"))
    return out


def _parse_other_listed(lines: list[str]) -> list[tuple[str, str, str]]:
    """otherlisted.txt fields: ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|
    Round Lot Size|Test Issue|NASDAQ Symbol
    """
    out = []
    if not lines:
        return out
    header = lines[0].split("|")
    idx_sym = header.index("ACT Symbol")
    idx_name = header.index("Security Name")
    idx_exch = header.index("Exchange")
    idx_test = header.index("Test Issue")
    idx_etf = header.index("ETF")
    for line in lines[1:]:
        if not line or line.startswith("File Creation Time"):
            continue
        parts = line.split("|")
        if len(parts) < len(header):
            continue
        sym = parts[idx_sym].strip()
        if not sym or any(c in sym for c in _JUNK_SYMBOL_CHARS):
            continue
        if parts[idx_test] == "Y":
            continue
        if parts[idx_etf] == "Y":
            continue
        name = _strip_corp_suffix(parts[idx_name])
        exch = _OTHER_EXCHANGES.get(parts[idx_exch], parts[idx_exch])
        out.append((sym, name, exch))
    return out


def main() -> int:
    print(f"Fetching {NASDAQ_LISTED_URL}", file=sys.stderr)
    nlines = _fetch(NASDAQ_LISTED_URL)
    print(f"Fetching {OTHER_LISTED_URL}", file=sys.stderr)
    olines = _fetch(OTHER_LISTED_URL)

    nrows = _parse_nasdaq_listed(nlines)
    orows = _parse_other_listed(olines)

    # De-dupe across files (same symbol can appear in both).
    seen: dict[str, tuple[str, str, str]] = {}
    for sym, name, exch in nrows + orows:
        if sym in seen:
            # Prefer the first occurrence (Nasdaq-listed beats other-listed
            # echo). Could also prefer richer name, but in practice they match.
            continue
        seen[sym] = (sym, name, exch)
    rows = sorted(seen.values(), key=lambda r: r[0])

    # Resolve output path. Try container path first, then host path.
    # __file__ = backend/scripts/build_tickers_directory.py
    # parents[1] = backend/  →  backend/data/tickers_directory.csv
    candidates = [
        Path("/app/data/tickers_directory.csv"),
        Path(__file__).resolve().parents[1] / "data" / "tickers_directory.csv",
    ]
    out_path = next((p for p in candidates if p.parent.exists()), candidates[-1])

    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "name", "exchange"])
        w.writerows(rows)

    print(
        f"Wrote {len(rows)} tickers to {out_path}  "
        f"(nasdaq={len(nrows)}, other={len(orows)})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
