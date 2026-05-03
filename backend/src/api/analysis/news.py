"""
News sentiment and market movers endpoints.

Provides news sentiment analysis and market mover tracking for
market awareness and trading signals.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException

from ...core.config import get_settings
from ...database.redis import RedisCache
from ...services.alphavantage_market_data import AlphaVantageMarketDataService
from ...services.alphavantage_response_formatter import AlphaVantageResponseFormatter
from ..health import get_redis
from ..models import (
    MarketMover,
    MarketMoversResponse,
    NewsArticle,
    NewsSentimentResponse,
    StockFundamentalsRequest,
)
from .shared import get_formatter, get_market_service

logger = structlog.get_logger()
router = APIRouter()


@router.post("/news-sentiment", response_model=NewsSentimentResponse)
async def news_sentiment(
    request: StockFundamentalsRequest,
    redis_cache: RedisCache = Depends(get_redis),
    market_service: AlphaVantageMarketDataService = Depends(get_market_service),
    formatter: AlphaVantageResponseFormatter = Depends(get_formatter),
) -> NewsSentimentResponse:
    """Get news sentiment for a stock."""
    try:
        from datetime import UTC, datetime

        current_date = datetime.now(UTC).strftime("%Y-%m-%d")
        cache_key = f"news_sentiment:{request.symbol}:{current_date}"
        cached_result = await redis_cache.get(cache_key)
        if cached_result:
            return NewsSentimentResponse.model_validate(cached_result)

        logger.info("Fetching news sentiment from Alpha Vantage", symbol=request.symbol)

        data = await market_service.get_news_sentiment(
            tickers=request.symbol, limit=50, sort="LATEST"
        )
        feed = data.get("feed", [])

        if not feed:
            raise ValueError(f"No news available for {request.symbol}")

        # Filter by sentiment
        positive = [
            NewsArticle(
                title=item["title"],
                url=item["url"],
                source=item.get("source", "Unknown"),
                sentiment_score=item["overall_sentiment_score"],
                sentiment_label="Bullish",
            )
            for item in feed
            if item.get("overall_sentiment_score", 0) > 0.15
        ][:3]

        negative = [
            NewsArticle(
                title=item["title"],
                url=item["url"],
                source=item.get("source", "Unknown"),
                sentiment_score=item["overall_sentiment_score"],
                sentiment_label="Bearish",
            )
            for item in feed
            if item.get("overall_sentiment_score", 0) < -0.15
        ][:3]

        overall = f"Found {len(positive)} positive and {len(negative)} negative articles for {request.symbol}"

        # Generate rich markdown using formatter
        formatted_markdown = formatter.format_news_sentiment(
            raw_data=data,
            symbol=request.symbol,
            invoked_at=datetime.now(UTC).isoformat(),
        )

        result = NewsSentimentResponse(
            symbol=request.symbol,
            positive_news=positive,
            negative_news=negative,
            overall_sentiment=overall,
            formatted_markdown=formatted_markdown,
        )

        settings = get_settings()
        await redis_cache.set(
            cache_key, result.model_dump(), ttl_seconds=settings.cache_ttl_news
        )
        logger.info("News sentiment completed", symbol=request.symbol)
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid symbol: {str(e)}") from e
    except Exception as e:
        logger.error("News sentiment failed", symbol=request.symbol, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"News sentiment failed: {str(e)}"
        ) from e


@router.get("/market-movers", response_model=MarketMoversResponse)
async def market_movers(
    redis_cache: RedisCache = Depends(get_redis),
    market_service: AlphaVantageMarketDataService = Depends(get_market_service),
    formatter: AlphaVantageResponseFormatter = Depends(get_formatter),
) -> MarketMoversResponse:
    """Get today's market movers (gainers, losers, most active)."""
    try:
        from datetime import UTC, datetime

        current_date = datetime.now(UTC).strftime("%Y-%m-%d")
        cache_key = f"market_movers:{current_date}"
        cached_result = await redis_cache.get(cache_key)
        if cached_result:
            return MarketMoversResponse.model_validate(cached_result)

        logger.info("Fetching market movers from Alpha Vantage")

        data = await market_service.get_top_gainers_losers()

        gainers = [
            MarketMover(
                ticker=item["ticker"],
                price=float(item["price"]),
                change_amount=float(item["change_amount"]),
                change_percentage=item["change_percentage"],
                volume=int(item["volume"]),
            )
            for item in data.get("top_gainers", [])[:5]
        ]

        losers = [
            MarketMover(
                ticker=item["ticker"],
                price=float(item["price"]),
                change_amount=float(item["change_amount"]),
                change_percentage=item["change_percentage"],
                volume=int(item["volume"]),
            )
            for item in data.get("top_losers", [])[:5]
        ]

        active = [
            MarketMover(
                ticker=item["ticker"],
                price=float(item["price"]),
                change_amount=float(item["change_amount"]),
                change_percentage=item["change_percentage"],
                volume=int(item["volume"]),
            )
            for item in data.get("most_actively_traded", [])[:5]
        ]

        # Generate rich markdown using formatter
        formatted_markdown = formatter.format_market_movers(
            raw_data=data,
            invoked_at=datetime.now(UTC).isoformat(),
        )

        result = MarketMoversResponse(
            top_gainers=gainers,
            top_losers=losers,
            most_active=active,
            last_updated=datetime.now(UTC).isoformat(),
            formatted_markdown=formatted_markdown,
        )

        settings = get_settings()
        await redis_cache.set(
            cache_key, result.model_dump(), ttl_seconds=settings.cache_ttl_news
        )
        logger.info("Market movers completed")
        return result

    except Exception as e:
        logger.error("Market movers failed", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Market movers failed: {str(e)}"
        ) from e
