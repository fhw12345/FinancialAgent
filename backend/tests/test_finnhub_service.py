"""Unit tests for FinnhubService — httpx mocked via respx-style patching."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.services.data_manager.types import DataFetchError
from src.services.finnhub import FinnhubService


def _make_service(monkeypatch) -> FinnhubService:
    svc = FinnhubService(api_key="TEST_KEY_123")
    return svc


def _mock_response(status_code: int, json_body) -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = status_code
    r.json = MagicMock(return_value=json_body)
    return r


class TestFinnhubServiceInit:
    def test_empty_key_raises(self):
        with pytest.raises(ValueError, match="non-empty api_key"):
            FinnhubService(api_key="")


class TestFetchQuote:
    @pytest.mark.asyncio
    async def test_success(self, monkeypatch):
        svc = _make_service(monkeypatch)
        body = {
            "c": 280.14,
            "d": 8.79,
            "dp": 3.24,
            "h": 287.22,
            "l": 278.37,
            "o": 278.85,
            "pc": 271.35,
            "t": 1714521600,
        }
        svc._client.get = AsyncMock(return_value=_mock_response(200, body))

        q = await svc.fetch_quote("AAPL")

        assert q.symbol == "AAPL"
        assert q.price == 280.14
        assert q.change == 8.79
        assert q.change_percent == 3.24
        assert q.previous_close == 271.35

    @pytest.mark.asyncio
    async def test_http_error(self, monkeypatch):
        svc = _make_service(monkeypatch)
        svc._client.get = AsyncMock(return_value=_mock_response(429, {}))

        with pytest.raises(DataFetchError, match="HTTP 429"):
            await svc.fetch_quote("AAPL")

    @pytest.mark.asyncio
    async def test_timeout_wrapped(self, monkeypatch):
        svc = _make_service(monkeypatch)
        svc._client.get = AsyncMock(side_effect=httpx.TimeoutException("slow"))

        with pytest.raises(DataFetchError, match="timeout"):
            await svc.fetch_quote("AAPL")

    @pytest.mark.asyncio
    async def test_empty_payload(self, monkeypatch):
        svc = _make_service(monkeypatch)
        # Finnhub returns c=0 for unknown symbols
        svc._client.get = AsyncMock(return_value=_mock_response(200, {"c": 0}))

        with pytest.raises(DataFetchError, match="empty"):
            await svc.fetch_quote("NOPE")


class TestFetchCompanyNews:
    @pytest.mark.asyncio
    async def test_success(self, monkeypatch):
        svc = _make_service(monkeypatch)
        body = [
            {"datetime": 1714521600, "headline": "Apple beats Q2", "source": "Reuters"},
            {"datetime": 1714435200, "headline": "Apple new launch", "source": "WSJ"},
        ]
        svc._client.get = AsyncMock(return_value=_mock_response(200, body))

        items = await svc.fetch_company_news("AAPL", "2026-04-01", "2026-05-01")

        assert len(items) == 2
        assert items[0].title == "Apple beats Q2"
        assert items[0].source == "Reuters"

    @pytest.mark.asyncio
    async def test_non_list_raises(self, monkeypatch):
        svc = _make_service(monkeypatch)
        svc._client.get = AsyncMock(return_value=_mock_response(200, {"error": "bad"}))

        with pytest.raises(DataFetchError):
            await svc.fetch_company_news("AAPL", "2026-04-01", "2026-05-01")


class TestFetchInsider:
    @pytest.mark.asyncio
    async def test_success(self, monkeypatch):
        svc = _make_service(monkeypatch)
        body = {
            "data": [
                {
                    "name": "Tim Cook",
                    "share": 1000,
                    "transactionCode": "S",
                    "transactionDate": "2026-04-15",
                }
            ],
            "symbol": "AAPL",
        }
        svc._client.get = AsyncMock(return_value=_mock_response(200, body))

        rows = await svc.fetch_insider_transactions("AAPL")

        assert len(rows) == 1
        assert rows[0]["name"] == "Tim Cook"

    @pytest.mark.asyncio
    async def test_empty_data(self, monkeypatch):
        svc = _make_service(monkeypatch)
        svc._client.get = AsyncMock(
            return_value=_mock_response(200, {"symbol": "AAPL"})
        )

        rows = await svc.fetch_insider_transactions("AAPL")
        assert rows == []
