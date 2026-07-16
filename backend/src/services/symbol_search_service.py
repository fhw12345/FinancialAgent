"""Reusable US-equity symbol search shared by APIs and agents."""

from __future__ import annotations

from typing import Any

import structlog

from ..data.sector_universe import load_universe
from ..data.tickers_directory import load_directory
from ..models.symbol_resolution import SymbolCandidate
from .market_data import yfinance_search

logger = structlog.get_logger()


def symbol_comparison_key(symbol: str) -> str:
    """Normalize a symbol for equality without changing provider formatting."""
    return symbol.strip().upper().replace("-", ".")


def search_local_symbols(query: str, limit: int = 10) -> list[SymbolCandidate]:
    """Search the committed symbol directories with deterministic ranking."""
    q_upper = query.strip().upper()
    q_lower = query.strip().lower()
    if not q_upper:
        return []

    def score(symbol: str, name: str) -> tuple[str, float] | None:
        symbol_upper = symbol.upper()
        name_lower = name.lower()
        if symbol_comparison_key(symbol_upper) == symbol_comparison_key(q_upper):
            return "exact_symbol", 1.0
        if name_lower == q_lower:
            return "exact_name", 0.95
        if symbol_upper.startswith(q_upper):
            return "symbol_prefix", 0.9
        if name_lower.startswith(q_lower):
            return "name_prefix", 0.8
        if q_upper in symbol_upper or q_lower in name_lower:
            return "fuzzy", 0.6
        return None

    scored: list[tuple[float, str, SymbolCandidate]] = []
    seen: set[str] = set()

    for row in load_universe():
        match = score(row.symbol, row.name)
        if match is None:
            continue
        match_type, confidence = match
        key = symbol_comparison_key(row.symbol)
        seen.add(key)
        scored.append(
            (
                confidence,
                row.symbol.upper(),
                SymbolCandidate(
                    symbol=row.symbol.upper(),
                    name=row.name,
                    type="Equity",
                    match_type=match_type,
                    confidence=confidence,
                ),
            )
        )

    for row in load_directory():
        key = symbol_comparison_key(row.symbol)
        if key in seen:
            continue
        match = score(row.symbol, row.name)
        if match is None:
            continue
        match_type, confidence = match
        scored.append(
            (
                confidence,
                row.symbol.upper(),
                SymbolCandidate(
                    symbol=row.symbol.upper(),
                    name=row.name,
                    exchange=row.exchange,
                    type="Equity",
                    match_type=match_type,
                    confidence=confidence,
                ),
            )
        )

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored[:limit]]


class SymbolSearchService:
    """Search local data first, then configured market-data fallbacks."""

    def __init__(self, market_service: Any | None = None) -> None:
        self._market_service = market_service

    async def search(self, query: str, limit: int = 10) -> list[SymbolCandidate]:
        """Return ranked, deduplicated candidates for a company or ticker."""
        normalized_query = query.strip()
        if not normalized_query:
            return []

        local_results = search_local_symbols(normalized_query, limit)
        if local_results:
            return local_results

        if self._market_service is not None:
            try:
                raw_results = await self._market_service.search_symbols(
                    normalized_query,
                    limit=limit,
                )
                provider_results = self._convert_results(raw_results, limit)
                if provider_results:
                    return provider_results
            except Exception as exc:
                logger.warning(
                    "symbol_search_provider_failed",
                    query=normalized_query,
                    error=str(exc),
                )

        try:
            raw_yfinance = await yfinance_search.search_symbols(
                normalized_query,
                limit=limit,
            )
            return self._convert_results(raw_yfinance, limit)
        except Exception as exc:
            logger.warning(
                "symbol_search_yfinance_failed",
                query=normalized_query,
                error=str(exc),
            )
            return []

    async def exact(self, symbol: str) -> SymbolCandidate | None:
        """Validate a symbol and return its exact directory/provider match."""
        query = symbol.strip().upper()
        if not query:
            return None
        expected_key = symbol_comparison_key(query)
        for candidate in await self.search(query, limit=10):
            if symbol_comparison_key(candidate.symbol) == expected_key:
                return SymbolCandidate(
                    symbol=query,
                    name=candidate.name,
                    exchange=candidate.exchange,
                    type=candidate.type,
                    match_type="exact_symbol",
                    confidence=1.0,
                )
        return None

    @staticmethod
    def _convert_results(
        raw_results: list[dict[str, Any]],
        limit: int,
    ) -> list[SymbolCandidate]:
        candidates: list[SymbolCandidate] = []
        seen: set[str] = set()
        for raw in raw_results:
            symbol = str(raw.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            key = symbol_comparison_key(symbol)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                SymbolCandidate(
                    symbol=symbol,
                    name=str(raw.get("name") or symbol),
                    exchange=str(raw.get("exchange") or ""),
                    type=str(raw.get("type") or "Equity"),
                    match_type=str(raw.get("match_type") or ""),
                    confidence=float(raw.get("confidence") or 0.0),
                )
            )
            if len(candidates) >= limit:
                break
        return candidates
