"""
Technical Analysis and Market Data Tools.

Provides tools for market movers, commodities, and technical indicators.
"""

from datetime import UTC, datetime

import structlog
from langchain_core.tools import tool

from src.services.alphavantage_market_data import AlphaVantageMarketDataService
from src.services.alphavantage_response_formatter import AlphaVantageResponseFormatter
from src.services.market_data import yfinance_indicators

logger = structlog.get_logger()


async def _resolve_indicator_df(
    service: AlphaVantageMarketDataService,
    symbol: str,
    indicator_upper: str,
    interval: str,
    time_period: int | None,
    av_series_type: str | None = "close",
):
    """yfinance-first → AV fallback. Returns (df, data_source) so the
    formatter can render which path served the response."""
    try:
        df = await yfinance_indicators.compute_indicator(
            symbol=symbol,
            function=indicator_upper,
            interval=interval,
            time_period=time_period,
        )
        if df.empty:
            raise RuntimeError("yfinance compute returned empty")
        return df, "yfinance_local"
    except Exception as yf_err:
        logger.warning(
            "yfinance indicator failed; falling back to Alpha Vantage",
            symbol=symbol,
            indicator=indicator_upper,
            interval=interval,
            error=str(yf_err),
        )
        df = await service.get_technical_indicator(
            symbol=symbol,
            function=indicator_upper,
            interval=interval,
            time_period=time_period,
            series_type=av_series_type,
        )
        return df, "alpha_vantage_fallback"


def create_technical_tools(
    service: AlphaVantageMarketDataService, formatter: AlphaVantageResponseFormatter
) -> list:
    """
    Create technical analysis and market data tools.

    Args:
        service: Initialized AlphaVantageMarketDataService instance
        formatter: AlphaVantageResponseFormatter for consistent markdown output

    Returns:
        List of technical analysis LangChain tools
    """

    @tool
    async def get_market_movers() -> str:
        """
        Get today's top market movers in the US stock market.

        Returns three categories of top performers:
        - Top Gainers: Stocks with highest price increase (% and $)
        - Top Losers: Stocks with largest price decrease (% and $)
        - Most Active: Stocks with highest trading volume

        Each category shows top 5 stocks with ticker, price, change, and volume.

        Args:
            None

        Returns:
            Compressed market movers summary (top 5 in each category)

        Examples:
            - Returns: NVDA +15.2%, TSLA -8.3%, AAPL 250M volume, etc.
        """
        try:
            data = await service.get_top_gainers_losers()

            if not data:
                return "No market movers data available"

            # Use formatter for consistent rich markdown output
            return formatter.format_market_movers(
                raw_data=data,
                invoked_at=datetime.now(UTC).isoformat(),
            )

        except Exception as e:
            logger.error("Market movers tool failed", error=str(e))
            return f"Market movers error: {str(e)}"

    @tool
    async def get_copper_commodity(interval: str = "monthly") -> str:
        """
        Get global copper prices (key indicator for AI infrastructure demand).

        Copper is essential for AI data center construction and electricity
        infrastructure. Rising copper prices indicate growing AI/tech demand.

        Args:
            interval: Price interval - "daily", "weekly", or "monthly"

        Returns:
            Formatted copper price history with trend analysis

        Examples:
            - interval="monthly" → Long-term copper price trends
            - interval="weekly" → Recent copper price movements

        Note:
            Copper demand correlates with AI infrastructure growth due to
            massive electricity requirements for GPU clusters and data centers.
        """
        try:
            df = await service.get_commodity_price(
                commodity="COPPER", interval=interval
            )

            if df.empty:
                return f"No copper price data available for interval: {interval}"

            return formatter.format_commodity_price(
                df=df,
                commodity="COPPER",
                interval=interval,
                invoked_at=datetime.now(UTC).isoformat(),
            )
        except Exception as e:
            logger.error(
                "Copper commodity tool failed", interval=interval, error=str(e)
            )
            return f"Copper commodity error: {str(e)}"

    @tool
    async def get_trend_indicator(
        symbol: str,
        indicator: str,
        interval: str = "daily",
        time_period: int = 10,
    ) -> str:
        """
        Get trend indicators: SMA, EMA, VWAP.

        Use for identifying price trends and support/resistance levels.
        Moving averages smooth price data to show trend direction.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL", "NVDA")
            indicator: Indicator name - "SMA", "EMA", or "VWAP"
            interval: Time interval - 1min, 5min, 15min, 30min, 60min, daily, weekly, monthly
            time_period: Period for calculation (default: 10 for SMA/EMA)

        Returns:
            Formatted trend indicator with current value and interpretation

        Examples:
            - symbol="AAPL", indicator="SMA" → 10-period SMA on daily chart
            - symbol="NVDA", indicator="EMA", interval="60min", time_period=20 → 20-period EMA hourly
            - symbol="TSLA", indicator="VWAP", interval="1min" → Intraday VWAP
        """
        try:
            supported = ["SMA", "EMA", "VWAP"]
            indicator_upper = indicator.upper()

            if indicator_upper not in supported:
                return f"Unsupported trend indicator: {indicator}. Use one of: {', '.join(supported)}"

            df, data_source = await _resolve_indicator_df(
                service=service,
                symbol=symbol,
                indicator_upper=indicator_upper,
                interval=interval,
                time_period=time_period if indicator_upper != "VWAP" else None,
            )

            if df.empty:
                return f"No {indicator} data available for {symbol}"

            return formatter.format_technical_indicator(
                df=df,
                symbol=symbol,
                function=indicator_upper,
                interval=interval,
                invoked_at=datetime.now(UTC).isoformat(),
                data_source=data_source,
            )
        except Exception as e:
            logger.error(
                "Trend indicator tool failed",
                symbol=symbol,
                indicator=indicator,
                error=str(e),
            )
            return f"Trend indicator error for {symbol} ({indicator}): {str(e)}"

    @tool
    async def get_momentum_indicator(
        symbol: str,
        indicator: str,
        interval: str = "daily",
        time_period: int = 14,
    ) -> str:
        """
        Get momentum indicators: RSI, MACD, STOCH.

        Use for identifying overbought/oversold conditions and trend reversals.
        Momentum indicators measure the speed of price changes.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL", "NVDA")
            indicator: Indicator name - "RSI", "MACD", or "STOCH"
            interval: Time interval - 1min, 5min, 15min, 30min, 60min, daily, weekly, monthly
            time_period: Period for calculation (default: 14 for RSI)

        Returns:
            Formatted momentum indicator with current value and trading signal

        Examples:
            - symbol="AAPL", indicator="RSI" → 14-period RSI (overbought >70, oversold <30)
            - symbol="NVDA", indicator="MACD", interval="60min" → Hourly MACD crossover signals
            - symbol="TSLA", indicator="STOCH" → Stochastic oscillator for reversal signals
        """
        try:
            supported = ["RSI", "MACD", "STOCH"]
            indicator_upper = indicator.upper()

            if indicator_upper not in supported:
                return f"Unsupported momentum indicator: {indicator}. Use one of: {', '.join(supported)}"

            df, data_source = await _resolve_indicator_df(
                service=service,
                symbol=symbol,
                indicator_upper=indicator_upper,
                interval=interval,
                time_period=time_period if indicator_upper == "RSI" else None,
            )

            if df.empty:
                return f"No {indicator} data available for {symbol}"

            return formatter.format_technical_indicator(
                df=df,
                symbol=symbol,
                function=indicator_upper,
                interval=interval,
                invoked_at=datetime.now(UTC).isoformat(),
                data_source=data_source,
            )
        except Exception as e:
            logger.error(
                "Momentum indicator tool failed",
                symbol=symbol,
                indicator=indicator,
                error=str(e),
            )
            return f"Momentum indicator error for {symbol} ({indicator}): {str(e)}"

    @tool
    async def get_volume_indicator(
        symbol: str,
        indicator: str,
        interval: str = "daily",
        time_period: int = 14,
    ) -> str:
        """
        Get volume/volatility indicators: AD, OBV, ADX, AROON, BBANDS.

        Use for confirming trends and measuring volatility.
        Volume indicators show buying/selling pressure and trend strength.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL", "NVDA")
            indicator: Indicator name - "AD", "OBV", "ADX", "AROON", or "BBANDS"
            interval: Time interval - 1min, 5min, 15min, 30min, 60min, daily, weekly, monthly
            time_period: Period for calculation (default: 14 for ADX/AROON, 20 for BBANDS)

        Returns:
            Formatted volume/volatility indicator with current value and interpretation

        Examples:
            - symbol="AAPL", indicator="AD" → Accumulation/Distribution Line
            - symbol="NVDA", indicator="OBV" → On-Balance Volume for trend confirmation
            - symbol="TSLA", indicator="ADX" → Trend strength (>25 = strong trend)
            - symbol="AAPL", indicator="BBANDS", time_period=20 → Bollinger Bands volatility
            - symbol="NVDA", indicator="AROON" → Aroon Up/Down for trend identification
        """
        try:
            supported = ["AD", "OBV", "ADX", "AROON", "BBANDS"]
            indicator_upper = indicator.upper()

            if indicator_upper not in supported:
                return f"Unsupported volume indicator: {indicator}. Use one of: {', '.join(supported)}"

            # Adjust default time_period for BBANDS
            if indicator_upper == "BBANDS" and time_period == 14:
                time_period = 20

            df, data_source = await _resolve_indicator_df(
                service=service,
                symbol=symbol,
                indicator_upper=indicator_upper,
                interval=interval,
                time_period=(
                    time_period if indicator_upper not in ["AD", "OBV"] else None
                ),
                av_series_type=(
                    "close" if indicator_upper not in ["AD", "OBV"] else None
                ),
            )

            if df.empty:
                return f"No {indicator} data available for {symbol}"

            return formatter.format_technical_indicator(
                df=df,
                symbol=symbol,
                function=indicator_upper,
                interval=interval,
                invoked_at=datetime.now(UTC).isoformat(),
                data_source=data_source,
            )
        except Exception as e:
            logger.error(
                "Volume indicator tool failed",
                symbol=symbol,
                indicator=indicator,
                error=str(e),
            )
            return f"Volume indicator error for {symbol} ({indicator}): {str(e)}"

    return [
        get_market_movers,
        get_copper_commodity,
        get_trend_indicator,
        get_momentum_indicator,
        get_volume_indicator,
    ]
