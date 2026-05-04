"""
Sector universe loader — reads backend/data/sector_universe.csv at import.

The CSV is built by scripts/build_sector_universe.py and committed to git.
Runtime is zero-network: just reads the file once into module-level lists.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import structlog

from ..models.portfolio_analysis import SectorUniverseRow

logger = structlog.get_logger(__name__)

DEFAULT_CSV_PATHS = [
    Path("/app/data/sector_universe.csv"),  # in container
    Path(__file__).resolve().parents[3] / "data" / "sector_universe.csv",  # source
]


def _resolve_path() -> Path:
    for p in DEFAULT_CSV_PATHS:
        if p.exists():
            return p
    raise FileNotFoundError(
        f"sector_universe.csv not found at any of: {DEFAULT_CSV_PATHS}"
    )


@lru_cache(maxsize=1)
def load_universe() -> list[SectorUniverseRow]:
    """Load universe rows once. Empty list if CSV is missing (loud warning)."""
    try:
        path = _resolve_path()
    except FileNotFoundError as e:
        logger.warning("sector_universe_missing", error=str(e))
        return []

    rows: list[SectorUniverseRow] = []
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                rows.append(
                    SectorUniverseRow(
                        symbol=r["symbol"],
                        name=r["name"],
                        sector=r["sector"],
                        industry=r["industry"],
                        market_cap_b=float(r["market_cap_b"] or 0),
                    )
                )
            except Exception as e:
                logger.warning("universe_row_skipped", row=r, error=str(e))
    logger.info("sector_universe_loaded", count=len(rows), source=str(path))
    return rows


def list_sectors() -> dict[str, list[str]]:
    """Return {sector: [industry, …]} derived from the loaded universe."""
    by_sector: dict[str, set[str]] = defaultdict(set)
    for r in load_universe():
        by_sector[r.sector].add(r.industry)
    return {s: sorted(inds) for s, inds in sorted(by_sector.items())}


def filter_universe(sectors: list[str]) -> list[SectorUniverseRow]:
    """Filter universe to rows whose sector is in the given list (exact match)."""
    if not sectors:
        return []
    sector_set = set(sectors)
    return [r for r in load_universe() if r.sector in sector_set]
