"""
Alpha Vantage fallback fetchers for fundamentals.

These helpers are split out of `fundamentals.py` so the mixin file stays under
the 500-line cap. They are not part of the public mixin — `FundamentalsMixin`
calls them only when yfinance fails AND `api_key` is configured.

Each helper takes the bound `mixin` (so it can reach `client`, `base_url`,
`api_key`, `_sanitize_*`) and returns the raw AV response dict, mirroring the
schema yfinance_fundamentals produces. They raise `ValueError` on AV failure;
the caller logs and re-raises so the fallback chain reports the right source.
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()


async def fetch_company_overview(mixin: Any, symbol: str) -> dict[str, Any]:
    response = await mixin.client.get(
        mixin.base_url,
        params={"function": "OVERVIEW", "symbol": symbol, "apikey": mixin.api_key},
    )
    if response.status_code != 200:
        raise ValueError(
            f"Alpha Vantage API error: {response.status_code} - "
            f"{mixin._sanitize_text(response.text)}"
        )
    data = response.json()
    if not data or "Symbol" not in data:
        raise ValueError(f"No company overview data for symbol: {symbol}")
    logger.info("Company overview via Alpha Vantage", symbol=symbol, company_name=data.get("Name", "N/A"))
    return data  # type: ignore[no-any-return]


async def fetch_cash_flow(mixin: Any, symbol: str) -> dict[str, Any]:
    response = await mixin.client.get(
        mixin.base_url,
        params={"function": "CASH_FLOW", "symbol": symbol, "apikey": mixin.api_key},
    )
    if response.status_code != 200:
        raise ValueError(
            f"Alpha Vantage API error: {response.status_code} - "
            f"{mixin._sanitize_text(response.text)}"
        )
    data = response.json()
    if "annualReports" not in data and "quarterlyReports" not in data:
        raise ValueError(f"No cash flow data for symbol: {symbol}")
    logger.info(
        "Cash flow via Alpha Vantage",
        symbol=symbol,
        annual_reports=len(data.get("annualReports", [])),
        quarterly_reports=len(data.get("quarterlyReports", [])),
    )
    return data  # type: ignore[no-any-return]


async def fetch_balance_sheet(mixin: Any, symbol: str) -> dict[str, Any]:
    response = await mixin.client.get(
        mixin.base_url,
        params={"function": "BALANCE_SHEET", "symbol": symbol, "apikey": mixin.api_key},
    )
    if response.status_code != 200:
        raise ValueError(
            f"Alpha Vantage API error: {response.status_code} - "
            f"{mixin._sanitize_text(response.text)}"
        )
    data = response.json()
    if "annualReports" not in data and "quarterlyReports" not in data:
        raise ValueError(f"No balance sheet data for symbol: {symbol}")
    logger.info(
        "Balance sheet via Alpha Vantage",
        symbol=symbol,
        annual_reports=len(data.get("annualReports", [])),
        quarterly_reports=len(data.get("quarterlyReports", [])),
    )
    return data  # type: ignore[no-any-return]


async def fetch_news_sentiment(
    mixin: Any,
    tickers: str | None,
    topics: str | None,
    limit: int,
    sort: str,
) -> dict[str, Any]:
    params: dict[str, str | int] = {
        "function": "NEWS_SENTIMENT",
        "limit": limit,
        "sort": sort,
        "apikey": mixin.api_key,
    }
    filter_desc = ""
    if tickers:
        params["tickers"] = tickers
        filter_desc = f"tickers={tickers}"
    if topics:
        params["topics"] = topics
        filter_desc = f"topics={topics}" if not filter_desc else f"{filter_desc}, topics={topics}"

    response = await mixin.client.get(mixin.base_url, params=params)
    if response.status_code != 200:
        raise ValueError(
            f"Alpha Vantage API error: {response.status_code} - "
            f"{mixin._sanitize_text(response.text)}"
        )
    data = response.json()
    if "feed" not in data:
        sanitized = mixin._sanitize_response(data)
        logger.warning("No news sentiment data", filter=filter_desc, response=sanitized)
        return {
            "feed": [],
            "sentiment_score_definition": data.get("sentiment_score_definition"),
        }
    logger.info("News sentiment via Alpha Vantage", filter=filter_desc, news_count=len(data["feed"]))
    return data  # type: ignore[no-any-return]


async def fetch_top_gainers_losers(mixin: Any) -> dict[str, Any]:
    response = await mixin.client.get(
        mixin.base_url,
        params={"function": "TOP_GAINERS_LOSERS", "apikey": mixin.api_key},
    )
    if response.status_code != 200:
        raise ValueError(
            f"Alpha Vantage API error: {response.status_code} - "
            f"{mixin._sanitize_text(response.text)}"
        )
    data = response.json()
    if not any(k in data for k in ["top_gainers", "top_losers", "most_actively_traded"]):
        raise ValueError(f"No market movers data available: {mixin._sanitize_response(data)}")
    logger.info(
        "Market movers via Alpha Vantage",
        gainers_count=len(data.get("top_gainers", [])),
        losers_count=len(data.get("top_losers", [])),
        active_count=len(data.get("most_actively_traded", [])),
    )
    return data  # type: ignore[no-any-return]
