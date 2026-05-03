"""
Company fundamentals and financial statements endpoints.

Handles company overview, news sentiment, and financial statement data.
"""

from functools import lru_cache
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from ...core.config import Settings
from ...services.alphavantage_market_data import AlphaVantageMarketDataService

router = APIRouter()
logger = structlog.get_logger()


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def get_market_service() -> AlphaVantageMarketDataService:
    """Dependency to get market data service."""
    return AlphaVantageMarketDataService(get_settings())


@router.get("/overview/{symbol}")
async def get_company_overview(
    symbol: str,
    service: AlphaVantageMarketDataService = Depends(get_market_service),
) -> dict[str, Any]:
    """
    Get comprehensive company overview and fundamentals.

    Returns raw Alpha Vantage OVERVIEW response including:
    - Company info (Symbol, Name, Description, Exchange, Currency)
    - Market metrics (MarketCapitalization, EBITDA, PERatio, EPS)
    - Financial ratios (ProfitMargin, RevenuePerShareTTM, DividendYield)
    - Price metrics (52WeekHigh, 52WeekLow, Beta, MovingAverages)
    """
    try:
        symbol = symbol.upper().strip()
        if not symbol:
            raise ValueError("Symbol is required")

        logger.info("Company overview request", symbol=symbol)

        data = await service.get_company_overview(symbol)

        logger.info(
            "Company overview fetched", symbol=symbol, company_name=data.get("Name")
        )

        return data

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Company overview fetch failed", symbol=symbol, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch company overview: {str(e)}"
        ) from e


@router.get("/news-sentiment/{symbol}")
async def get_news_sentiment(
    symbol: str,
    service: AlphaVantageMarketDataService = Depends(get_market_service),
    limit: int = Query(50, ge=1, le=1000, description="Max news items (1-1000)"),
    sort: str = Query(
        "LATEST", description="Sort order: LATEST | EARLIEST | RELEVANCE"
    ),
) -> dict[str, Any]:
    """
    Get news articles with sentiment analysis for a stock.

    Returns news feed with:
    - Title, URL, published time, summary, source
    - Overall sentiment score and label (Bullish/Bearish/Neutral)
    - Ticker-specific sentiment scores
    - Relevance scores
    """
    try:
        symbol = symbol.upper().strip()
        if not symbol:
            raise ValueError("Symbol is required")

        logger.info("News sentiment request", symbol=symbol, limit=limit)

        data = await service.get_news_sentiment(tickers=symbol, limit=limit, sort=sort)

        logger.info(
            "News sentiment fetched",
            symbol=symbol,
            news_count=len(data.get("feed", [])),
        )

        return data

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("News sentiment fetch failed", symbol=symbol, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch news sentiment: {str(e)}"
        ) from e


@router.get("/cash-flow/{symbol}")
async def get_cash_flow(
    symbol: str,
    service: AlphaVantageMarketDataService = Depends(get_market_service),
) -> dict[str, Any]:
    """
    Get cash flow statements (annual and quarterly).

    Returns:
    - annualReports: List of annual cash flow statements
    - quarterlyReports: List of quarterly cash flow statements

    Each report includes:
    - operatingCashflow, capitalExpenditures
    - cashflowFromInvestment, cashflowFromFinancing
    - dividendPayout, changeInCashAndCashEquivalents
    """
    try:
        symbol = symbol.upper().strip()
        if not symbol:
            raise ValueError("Symbol is required")

        logger.info("Cash flow request", symbol=symbol)

        data = await service.get_cash_flow(symbol)

        logger.info(
            "Cash flow fetched",
            symbol=symbol,
            annual_count=len(data.get("annualReports", [])),
            quarterly_count=len(data.get("quarterlyReports", [])),
        )

        return data

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Cash flow fetch failed", symbol=symbol, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch cash flow: {str(e)}"
        ) from e


@router.get("/balance-sheet/{symbol}")
async def get_balance_sheet(
    symbol: str,
    service: AlphaVantageMarketDataService = Depends(get_market_service),
) -> dict[str, Any]:
    """
    Get balance sheet statements (annual and quarterly).

    Returns:
    - annualReports: List of annual balance sheets
    - quarterlyReports: List of quarterly balance sheets

    Each report includes:
    - totalAssets, totalLiabilities, totalShareholderEquity
    - cash, currentDebt, longTermDebt
    - inventory, goodwill, intangibleAssets
    """
    try:
        symbol = symbol.upper().strip()
        if not symbol:
            raise ValueError("Symbol is required")

        logger.info("Balance sheet request", symbol=symbol)

        data = await service.get_balance_sheet(symbol)

        logger.info(
            "Balance sheet fetched",
            symbol=symbol,
            annual_count=len(data.get("annualReports", [])),
            quarterly_count=len(data.get("quarterlyReports", [])),
        )

        return data

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Balance sheet fetch failed", symbol=symbol, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch balance sheet: {str(e)}"
        ) from e
