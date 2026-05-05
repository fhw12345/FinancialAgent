"""
Macro market sentiment analysis engine.
Analyzes economic indicators from AlphaVantage for market sentiment assessment.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

import pandas as pd
import structlog

from ...api.models import MacroSentimentResponse

if TYPE_CHECKING:
    from ...services.alphavantage_market_data import AlphaVantageMarketDataService

logger = structlog.get_logger()


class MacroAnalyzer:
    """Macro market sentiment analyzer using AlphaVantage economic indicators."""

    def __init__(self, market_service: "AlphaVantageMarketDataService") -> None:
        self.market_service = market_service
        self.commodity_data: pd.DataFrame | None = None
        self.economic_indicators: dict[str, pd.DataFrame] = {}

    async def analyze(
        self, include_sectors: bool = True, include_indices: bool = True
    ) -> MacroSentimentResponse:
        """
        Analyze macro market sentiment using AlphaVantage economic indicators.

        Args:
            include_sectors: Include sector rotation analysis (deprecated, kept for API compatibility)
            include_indices: Include economic indicators analysis

        Returns:
            MacroSentimentResponse with complete sentiment analysis
        """
        try:
            logger.info("Starting macro sentiment analysis with AlphaVantage")

            # Fetch economic indicators
            (
                commodity_level,
                commodity_interpretation,
                fear_greed_score,
            ) = await self._analyze_commodity_prices()

            # Get economic indicators performance
            economic_indicators = {}
            if include_indices:
                economic_indicators = await self._analyze_economic_indicators()

            # Overall sentiment assessment
            market_sentiment = self._assess_overall_sentiment(
                fear_greed_score, economic_indicators
            )
            confidence_level = self._calculate_confidence(
                commodity_level, economic_indicators, {}
            )

            # Generate insights
            sentiment_summary, market_outlook, key_factors = (
                self._generate_macro_insights(
                    commodity_level,
                    commodity_interpretation,
                    economic_indicators,
                    {},
                )
            )

            response = MacroSentimentResponse(
                analysis_date=datetime.now(UTC).isoformat(),
                vix_level=commodity_level,
                vix_interpretation=commodity_interpretation,
                fear_greed_score=fear_greed_score,
                major_indices=economic_indicators,
                sector_performance={},  # Not available with economic indicators
                market_sentiment=market_sentiment,
                confidence_level=confidence_level,
                sentiment_summary=sentiment_summary,
                market_outlook=market_outlook,
                key_factors=key_factors,
            )

            logger.info(
                "Macro sentiment analysis completed", sentiment=market_sentiment
            )
            return response

        except Exception as e:
            logger.error("Macro sentiment analysis failed", error=str(e))
            raise

    async def _analyze_commodity_prices(self) -> tuple[float, str, int]:
        """Analyze commodity prices (WTI) as a market sentiment proxy."""
        try:
            # Fetch WTI commodity prices
            commodity_df = await self.market_service.get_commodity_prices(
                interval="monthly"
            )
            self.commodity_data = commodity_df

            if commodity_df.empty:
                logger.warning("No commodity data available, using default values")
                return 70.0, "neutral", 50

            # Get recent price changes (last 3 months vs previous 3 months)
            latest_values = commodity_df["value"].iloc[-3:].mean()
            previous_values = commodity_df["value"].iloc[-6:-3].mean()

            # Calculate percentage change
            pct_change = ((latest_values - previous_values) / previous_values) * 100

            # Map to sentiment score (inverted: rising commodities = fear, falling = greed)
            if pct_change > 10:
                interpretation = "rising_fast"
                fear_greed_score = 30  # More fear
            elif pct_change > 5:
                interpretation = "rising"
                fear_greed_score = 40
            elif pct_change > -5:
                interpretation = "neutral"
                fear_greed_score = 50
            elif pct_change > -10:
                interpretation = "falling"
                fear_greed_score = 60
            else:
                interpretation = "falling_fast"
                fear_greed_score = 70  # More greed

            logger.info(
                "Commodity price analysis completed",
                level=latest_values,
                interpretation=interpretation,
                pct_change=pct_change,
            )

            return float(latest_values), interpretation, fear_greed_score

        except Exception as e:
            logger.error("Commodity price analysis failed", error=str(e))
            # Return neutral default values
            return 70.0, "neutral", 50

    async def _analyze_economic_indicators(self) -> dict[str, float]:
        """Analyze economic indicators (GDP, CPI, Inflation, Unemployment)."""
        try:
            indicators = {}

            # Fetch all economic indicators
            try:
                gdp_df = await self.market_service.get_real_gdp(interval="quarterly")
                if not gdp_df.empty:
                    # Calculate YoY growth
                    latest_gdp = gdp_df["value"].iloc[-1]
                    year_ago_gdp = (
                        gdp_df["value"].iloc[-4] if len(gdp_df) >= 4 else latest_gdp
                    )
                    gdp_growth = ((latest_gdp - year_ago_gdp) / year_ago_gdp) * 100
                    indicators["Real GDP Growth (YoY)"] = round(gdp_growth, 2)
                    self.economic_indicators["GDP"] = gdp_df
            except Exception as e:
                logger.warning("Failed to fetch GDP data", error=str(e))

            try:
                cpi_df = await self.market_service.get_cpi(interval="monthly")
                if not cpi_df.empty:
                    # Calculate MoM change
                    latest_cpi = cpi_df["value"].iloc[-1]
                    prev_cpi = (
                        cpi_df["value"].iloc[-2] if len(cpi_df) >= 2 else latest_cpi
                    )
                    cpi_change = ((latest_cpi - prev_cpi) / prev_cpi) * 100
                    indicators["CPI (MoM)"] = round(cpi_change, 2)
                    self.economic_indicators["CPI"] = cpi_df
            except Exception as e:
                logger.warning("Failed to fetch CPI data", error=str(e))

            try:
                inflation_df = await self.market_service.get_inflation()
                if not inflation_df.empty:
                    latest_inflation = inflation_df["value"].iloc[-1]
                    indicators["Inflation Rate"] = round(latest_inflation, 2)
                    self.economic_indicators["Inflation"] = inflation_df
            except Exception as e:
                logger.warning("Failed to fetch inflation data", error=str(e))

            try:
                unemployment_df = await self.market_service.get_unemployment()
                if not unemployment_df.empty:
                    latest_unemployment = unemployment_df["value"].iloc[-1]
                    indicators["Unemployment Rate"] = round(latest_unemployment, 2)
                    self.economic_indicators["Unemployment"] = unemployment_df
            except Exception as e:
                logger.warning("Failed to fetch unemployment data", error=str(e))

            logger.info(
                "Economic indicators analysis completed",
                indicators_count=len(indicators),
            )

            return indicators

        except Exception as e:
            logger.error("Economic indicators analysis failed", error=str(e))
            return {}

    def _assess_overall_sentiment(
        self, fear_greed_score: int, major_indices: dict[str, float]
    ) -> Literal["fearful", "neutral", "greedy"]:
        """Assess overall market sentiment."""
        # Weight fear/greed score and market performance
        if major_indices:
            avg_performance = sum(major_indices.values()) / len(major_indices)
            if avg_performance > 1.0 and fear_greed_score > 60:
                return "greedy"
            elif avg_performance < -1.0 and fear_greed_score < 40:
                return "fearful"
            else:
                return "neutral"
        else:
            # Fallback to VIX-only assessment
            if fear_greed_score > 60:
                return "greedy"
            elif fear_greed_score < 40:
                return "fearful"
            else:
                return "neutral"

    def _calculate_confidence(
        self,
        vix_level: float,
        major_indices: dict[str, float],
        sector_performance: dict[str, float],
    ) -> float:
        """Calculate confidence in sentiment analysis."""
        data_quality = 0.7  # Base confidence

        # Boost confidence if we have good data coverage
        if major_indices and len(major_indices) > 3:
            data_quality += 0.1
        if sector_performance and len(sector_performance) > 5:
            data_quality += 0.1

        # Reduce confidence for extreme VIX readings (potential data issues)
        if vix_level > 50 or vix_level < 10:
            data_quality -= 0.2

        return min(1.0, max(0.0, data_quality))

    def _generate_macro_insights(
        self,
        vix_level: float,
        vix_interpretation: str,
        major_indices: dict[str, float],
        sector_performance: dict[str, float],
    ) -> tuple[str, str, list[str]]:
        """Generate human-readable macro insights for economic indicators."""

        # Sentiment summary based on commodity prices and economic data
        sentiment_summary = f"Economic conditions showing {vix_interpretation} commodity prices (WTI: ${vix_level:.2f}/barrel). "

        if major_indices:
            # Count growth vs absolute indicators
            growth_indicators = [
                k
                for k in major_indices.keys()
                if "Growth" in k or "MoM" in k or "YoY" in k
            ]
            if growth_indicators:
                sentiment_summary += (
                    f"Economic indicators tracked: {len(major_indices)} metrics. "
                )

        # Market outlook based on commodity price trends
        if vix_level > 80:
            outlook = "High commodity prices may indicate inflationary pressures and economic expansion."
        elif vix_level < 50:
            outlook = "Lower commodity prices may suggest economic slowdown or reduced demand."
        else:
            outlook = "Moderate commodity prices indicate stable economic conditions."

        # Key factors - format economic indicators correctly
        key_factors = [
            f"WTI Crude Oil: ${vix_level:.2f}/barrel ({vix_interpretation})",
        ]

        if major_indices:
            # Format each indicator appropriately
            for indicator, value in sorted(major_indices.items()):
                if "Growth" in indicator or "MoM" in indicator or "YoY" in indicator:
                    # These are percentage changes
                    key_factors.append(f"{indicator}: {value:+.2f}%")
                elif "Rate" in indicator:
                    # These are absolute percentages
                    key_factors.append(f"{indicator}: {abs(value):.1f}%")
                else:
                    # Generic format
                    key_factors.append(f"{indicator}: {value:.2f}")

        return sentiment_summary, outlook, key_factors
