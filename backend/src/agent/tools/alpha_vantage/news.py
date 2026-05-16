"""
News Sentiment Analysis Tools.

Provides tools for fetching news articles with sentiment analysis.
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from langchain_core.tools import tool

from src.services.alphavantage_market_data import AlphaVantageMarketDataService
from src.services.alphavantage_response_formatter import AlphaVantageResponseFormatter

logger = structlog.get_logger()


def _av_news_latest_asof(data: dict[str, Any]) -> datetime | None:
    """Pick the most recent ``time_published`` across the AV news feed.

    AV NEWS_SENTIMENT items carry ``time_published`` in the ugly
    ``YYYYMMDDTHHMMSS`` format; we tolerate missing / malformed entries
    by skipping them rather than throwing.
    """
    feed = data.get("feed") or []
    latest: datetime | None = None
    for item in feed:
        raw = item.get("time_published")
        if not isinstance(raw, str) or len(raw) < 8:
            continue
        try:
            dt = datetime.strptime(raw, "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
        except ValueError:
            continue
        if latest is None or dt > latest:
            latest = dt
    return latest


def create_news_tools(
    service: AlphaVantageMarketDataService, formatter: AlphaVantageResponseFormatter
) -> list:
    """
    Create news sentiment analysis tools.

    Args:
        service: Initialized AlphaVantageMarketDataService instance
        formatter: AlphaVantageResponseFormatter for consistent markdown output

    Returns:
        List of news analysis LangChain tools
    """

    @tool
    async def get_news_sentiment(
        symbol: str,
        max_positive: int = 3,
        max_negative: int = 3,
    ) -> str:
        """
        Get latest news articles with sentiment analysis for a stock.

        Returns filtered news feed with sentiment scores and classifications.
        Automatically filters to top positive and negative sentiment articles.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL", "MSFT")
            max_positive: Maximum positive sentiment articles to return (default: 3)
            max_negative: Maximum negative sentiment articles to return (default: 3)

        Returns:
            Compressed news sentiment summary with top positive/negative articles

        Sentiment Labels:
            - Bullish: Positive sentiment (score > 0.15)
            - Bearish: Negative sentiment (score < -0.15)
            - Neutral: Mixed or neutral sentiment (-0.15 to 0.15)

        Examples:
            - symbol="AAPL" → Latest Apple news with sentiment
            - symbol="TSLA", max_positive=2, max_negative=2 → Tesla top 4 news
        """
        try:
            data = await service.get_news_sentiment(
                tickers=symbol,
                limit=50,  # Get more to filter best positive/negative
                sort="LATEST",
            )

            if not data.get("feed"):
                return f"No news sentiment data available for {symbol}"

            body = formatter.format_news_sentiment(
                raw_data=data,
                symbol=symbol,
                invoked_at=datetime.now(UTC).isoformat(),
            )

            # W3.4 provenance footnote — asof = newest headline so the
            # LLM can tell at citation time whether the bucket is fresh.
            asof = _av_news_latest_asof(data) or datetime.now(UTC)
            asof_day = asof.strftime("%Y-%m-%d")
            asof_repr = asof.strftime("%Y-%m-%dT%H:%MZ")
            sid = f"AV-N-{symbol.upper()}-{asof_day}"
            return f"{body}\n\nSource: alphavantage [{sid}] asof {asof_repr}"

        except Exception as e:
            logger.error("News sentiment tool failed", symbol=symbol, error=str(e))
            return f"News sentiment error for {symbol}: {str(e)}"

    return [get_news_sentiment]
