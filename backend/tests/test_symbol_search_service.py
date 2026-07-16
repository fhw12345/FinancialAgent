"""Tests for reusable symbol-search ranking and provider fallback."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.market.search import get_symbol_search_service, router
from src.models.symbol_resolution import SymbolCandidate
from src.services import symbol_search_service as module
from src.services.symbol_search_service import (
    SymbolSearchService,
    search_local_symbols,
)


def test_local_search_ranks_exact_name_and_deduplicates(monkeypatch):
    monkeypatch.setattr(
        module,
        "load_universe",
        lambda: [
            SimpleNamespace(
                symbol="AAPL",
                name="Apple Inc.",
            )
        ],
    )
    monkeypatch.setattr(
        module,
        "load_directory",
        lambda: [
            SimpleNamespace(symbol="AAPL", name="Apple Inc.", exchange="NASDAQ"),
            SimpleNamespace(symbol="APLE", name="Apple Hospitality", exchange="NYSE"),
        ],
    )

    results = search_local_symbols("Apple Inc.", limit=10)

    assert [item.symbol for item in results] == ["AAPL"]
    assert results[0].match_type == "exact_name"
    assert results[0].confidence == 0.95


def test_local_search_uses_deterministic_symbol_tiebreak(monkeypatch):
    monkeypatch.setattr(module, "load_universe", lambda: [])
    monkeypatch.setattr(
        module,
        "load_directory",
        lambda: [
            SimpleNamespace(symbol="AAC", name="Alpha C", exchange="NYSE"),
            SimpleNamespace(symbol="AAA", name="Alpha A", exchange="NYSE"),
        ],
    )

    results = search_local_symbols("AA", limit=10)

    assert [item.symbol for item in results] == ["AAA", "AAC"]


@pytest.mark.asyncio
async def test_provider_is_used_when_local_search_is_empty(monkeypatch):
    monkeypatch.setattr(module, "search_local_symbols", lambda query, limit: [])
    market_service = SimpleNamespace(
        search_symbols=AsyncMock(
            return_value=[
                {
                    "symbol": "CRWV",
                    "name": "CoreWeave",
                    "exchange": "NASDAQ",
                    "type": "Equity",
                    "match_type": "exact_symbol",
                    "confidence": 1.0,
                }
            ]
        )
    )
    service = SymbolSearchService(market_service)

    results = await service.search("CRWV")

    assert results[0].symbol == "CRWV"
    market_service.search_symbols.assert_awaited_once_with("CRWV", limit=10)


@pytest.mark.asyncio
async def test_yfinance_fallback_is_used_after_provider_failure(monkeypatch):
    monkeypatch.setattr(module, "search_local_symbols", lambda query, limit: [])
    monkeypatch.setattr(
        module.yfinance_search,
        "search_symbols",
        AsyncMock(
            return_value=[
                {
                    "symbol": "CRWV",
                    "name": "CoreWeave",
                    "exchange": "NMS",
                    "type": "equity",
                    "match_type": "exact_symbol",
                    "confidence": 1.0,
                }
            ]
        ),
    )
    market_service = SimpleNamespace(
        search_symbols=AsyncMock(side_effect=RuntimeError("provider offline"))
    )
    service = SymbolSearchService(market_service)

    results = await service.search("CRWV")

    assert results[0].symbol == "CRWV"


@pytest.mark.asyncio
async def test_yfinance_failure_degrades_to_empty_candidates(monkeypatch):
    monkeypatch.setattr(module, "search_local_symbols", lambda query, limit: [])
    monkeypatch.setattr(
        module.yfinance_search,
        "search_symbols",
        AsyncMock(side_effect=RuntimeError("yfinance offline")),
    )
    market_service = SimpleNamespace(
        search_symbols=AsyncMock(side_effect=RuntimeError("provider offline"))
    )

    results = await SymbolSearchService(market_service).search("UNKNOWN")

    assert results == []


@pytest.mark.asyncio
async def test_exact_accepts_equivalent_class_share_separator(monkeypatch):
    monkeypatch.setattr(
        module,
        "search_local_symbols",
        lambda query, limit: [
            module.SymbolCandidate(
                symbol="BRK.B",
                name="Berkshire Hathaway",
                confidence=1.0,
                match_type="exact_symbol",
            )
        ],
    )
    service = SymbolSearchService()

    result = await service.exact("BRK-B")

    assert result is not None
    assert result.symbol == "BRK-B"


def test_market_search_endpoint_preserves_response_contract():
    app = FastAPI()
    app.include_router(router)
    service = SimpleNamespace(
        search=AsyncMock(
            return_value=[
                SymbolCandidate(
                    symbol="AAPL",
                    name="Apple Inc.",
                    exchange="NASDAQ",
                    type="Equity",
                    match_type="exact_symbol",
                    confidence=1.0,
                )
            ]
        )
    )
    app.dependency_overrides[get_symbol_search_service] = lambda: service

    response = TestClient(app).get("/search?q=AAPL")

    assert response.status_code == 200
    assert response.json() == {
        "query": "AAPL",
        "results": [
            {
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "exchange": "NASDAQ",
                "type": "Equity",
                "match_type": "exact_symbol",
                "confidence": 1.0,
            }
        ],
    }
