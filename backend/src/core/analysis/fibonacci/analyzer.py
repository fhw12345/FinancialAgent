"""
Main Fibonacci analysis engine with modular architecture.
Orchestrates trend detection, level calculation, and pressure zone analysis using specialized components.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pandas as pd
import structlog

from ....api.models import FibonacciAnalysisResponse
from .config import TimeframeConfig, TimeframeConfigs
from .level_calculator import LevelCalculator
from .trend_detector import TrendDetector

if TYPE_CHECKING:
    from ....services.data_manager import DataManager

logger = structlog.get_logger()


class FibonacciAnalyzer:
    """Advanced Fibonacci pressure level analyzer with modular architecture."""

    def __init__(self, data_manager: "DataManager") -> None:
        """
        Initialize analyzer with DataManager for cached OHLCV access.

        Args:
            data_manager: DataManager for all market data (uses Redis caching for daily+)
        """
        self.data_manager = data_manager
        self.data: pd.DataFrame | None = None
        self.symbol: str = ""
        self.timeframe: str = "1d"
        self.config: TimeframeConfig | None = None
        self.trend_detector: TrendDetector | None = None
        self.level_calculator = LevelCalculator()

    async def analyze(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        timeframe: str = "1d",
    ) -> FibonacciAnalysisResponse:
        """
        Perform advanced Fibonacci pressure level analysis with timeframe adaptation.

        Args:
            symbol: Stock symbol to analyze
            start_date: Start date for analysis (YYYY-MM-DD format)
            end_date: End date for analysis (YYYY-MM-DD format)
            timeframe: Timeframe for analysis ('1h', '1d', '1w', '1M')

        Returns:
            FibonacciAnalysisResponse with advanced pressure level analysis
        """
        try:
            logger.info(
                "Starting advanced Fibonacci pressure analysis",
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
            )

            # Initialize components
            self.symbol = symbol.upper()
            self.timeframe = timeframe
            self.config = TimeframeConfigs.get_config(timeframe)
            self.trend_detector = TrendDetector(self.config)

            # Fetch stock data with timeframe-appropriate interval
            stock_data = await self._fetch_stock_data(start_date, end_date)
            if stock_data is None or stock_data.empty:
                raise ValueError(
                    f"'{symbol}' is not a valid stock symbol or the stock may be delisted."
                )

            self.data = stock_data

            # Validate sufficient data for analysis
            min_data_points = self._get_minimum_data_points(timeframe)
            if len(self.data) < min_data_points:
                raise ValueError(
                    f"Insufficient data for {timeframe} Fibonacci analysis. "
                    f"Got {len(self.data)} bars, need at least {min_data_points} "
                    f"(calculated as {timeframe} swing_lookback × 3). "
                    f"This ensures enough data for trend pattern detection."
                )

            # Detect top trends using directional greedy accumulation
            top_trends = self.trend_detector.detect_top_trends(self.data)

            # Use the most significant trend for main analysis
            primary_trend = top_trends[0] if top_trends else None
            if not primary_trend:
                raise ValueError(
                    f"Could not identify any significant trends in the data for {symbol} on {timeframe} timeframe. "
                    f"This typically happens when: (1) insufficient price movement in the available data, "
                    f"(2) the stock is moving sideways with low volatility, "
                    f"or (3) the date range doesn't capture a complete trend cycle. "
                    f"Consider using a longer date range or different timeframe (1h or 1d)."
                )

            # Calculate analysis components
            current_price = float(stock_data["Close"].iloc[-1])

            # Create market structure from primary trend
            market_structure = self.level_calculator.create_market_structure(
                primary_trend, current_price
            )

            # Calculate Fibonacci levels for primary trend
            fibonacci_levels = self.level_calculator.calculate_fibonacci_levels(
                primary_trend
            )

            # Calculate confidence score
            confidence_score = self.level_calculator.calculate_confidence_score(
                top_trends, current_price
            )

            # Calculate golden ratio pressure zone
            pressure_zone = self.level_calculator.calculate_golden_pressure_zone(
                primary_trend
            )

            # Generate enhanced insights with pressure levels
            analysis_summary, key_insights = self._generate_pressure_insights(
                top_trends, fibonacci_levels, current_price
            )

            # Enhanced raw data with top 3 trends
            raw_data = self._build_raw_data(stock_data, top_trends, timeframe)

            response = FibonacciAnalysisResponse(
                symbol=self.symbol,
                start_date=start_date,
                end_date=end_date,
                timeframe=timeframe,
                current_price=current_price,
                analysis_date=datetime.now(UTC).isoformat(),
                fibonacci_levels=fibonacci_levels,
                market_structure=market_structure,
                confidence_score=confidence_score,
                pressure_zone=pressure_zone,
                trend_strength=self.level_calculator.assess_trend_strength(top_trends),
                analysis_summary=analysis_summary,
                key_insights=key_insights,
                raw_data=raw_data,
            )

            logger.info(
                "Advanced Fibonacci pressure analysis completed",
                symbol=self.symbol,
                timeframe=timeframe,
                top_trends_count=len(top_trends),
                confidence=confidence_score,
            )

            return response

        except Exception as e:
            logger.error("Fibonacci analysis failed", symbol=symbol, error=str(e))
            raise

    def _get_minimum_data_points(self, timeframe: str) -> int:
        """
        Calculate minimum required data points based on algorithm requirements.

        Instead of hardcoded values, calculates based on swing_lookback parameter
        from the timeframe config. This ensures minimums scale with algorithm needs.

        Formula: swing_lookback * 3 (ensures enough bars for trend pattern detection)
        Floor: 20 bars minimum (absolute minimum for any meaningful analysis)

        Results:
        - 1m: 10 * 3 = 30 bars (~30 minutes)
        - 1h: 5 * 3 = 15 → max(15, 20) = 20 bars (~20 hours)
        - 1d: 3 * 3 = 9 → max(9, 20) = 20 bars (~20 days)
        - 1w: 2 * 3 = 6 → max(6, 20) = 20 bars (~20 weeks)
        - 1M: 1 * 3 = 3 → max(3, 20) = 20 bars (~20 months)
        """
        config = TimeframeConfigs.get_config(timeframe)
        # Need at least 3x swing_lookback for meaningful trend detection
        calculated_min = config.swing_lookback * 3
        return max(calculated_min, 20)

    async def _fetch_stock_data(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> pd.DataFrame:
        """
        Fetch stock data via DataManager (with Redis caching for daily+).

        DataManager handles all granularities:
        - Intraday (1min-15min): No cache, always fresh
        - 30min-60min: Short TTL (5-15 min)
        - Daily+: Standard TTL (1-4 hours)
        """
        try:
            from datetime import datetime as dt
            from datetime import timedelta

            # Map timeframe to DataManager granularity
            granularity_map = {
                "1m": "1min",
                "1h": "60min",
                "4h": "60min",  # Use 60min and aggregate if needed
                "1d": "daily",
                "1w": "weekly",
                "1M": "monthly",
            }
            granularity = granularity_map.get(self.timeframe, "daily")

            logger.info(
                "Fetching OHLCV via DataManager",
                symbol=self.symbol,
                granularity=granularity,
            )

            ohlcv_list = await self.data_manager.get_ohlcv(
                symbol=self.symbol,
                granularity=granularity,
                outputsize="full",  # Need full data for trend detection
            )

            if not ohlcv_list:
                logger.error("No data returned from DataManager", symbol=self.symbol)
                return pd.DataFrame()

            # Convert OHLCVData list to DataFrame
            data = pd.DataFrame(
                [
                    {
                        "Open": d.open,
                        "High": d.high,
                        "Low": d.low,
                        "Close": d.close,
                        "Volume": d.volume,
                    }
                    for d in ohlcv_list
                ],
                # `pd.to_datetime(..., utc=True)` normalizes a list that may mix
                # naive and tz-aware datetimes (e.g. old cache entries vs fresh
                # yfinance pulls) into a single UTC-aware DatetimeIndex.
                index=pd.to_datetime([d.date for d in ohlcv_list], utc=True),
            )

            # Sort by date ascending (oldest first) for trend detection
            data = data.sort_index()

            # Apply date filters if provided
            if start_date:
                start_dt = pd.Timestamp(start_date, tz=UTC)
                data = data[data.index >= start_dt]
            elif self.timeframe == "1d":
                # Default to 1 year lookback for daily timeframe
                one_year_ago = dt.now(UTC) - timedelta(days=365)
                data = data[data.index >= pd.Timestamp(one_year_ago)]
                logger.info(
                    "Defaulting to 1-year lookback for daily Fibonacci analysis",
                    symbol=self.symbol,
                )

            if end_date:
                end_dt = pd.Timestamp(end_date, tz=UTC)
                data = data[data.index <= end_dt]

            logger.info(
                "Fetched stock data via DataManager",
                symbol=self.symbol,
                timeframe=self.timeframe,
                granularity=granularity,
                data_points=len(data),
                start=data.index[0] if len(data) > 0 else None,
                end=data.index[-1] if len(data) > 0 else None,
            )

            return data.dropna()

        except Exception as e:
            logger.error("Failed to fetch stock data", symbol=self.symbol, error=str(e))
            raise

    def _generate_pressure_insights(
        self,
        trends: list[dict[str, Any]],
        fibonacci_levels: list[Any],
        current_price: float,
    ) -> tuple[str, list[str]]:
        """Generate analysis insights focused on pressure zones and trend strength."""
        if not trends:
            return "No significant trends detected.", []

        primary_trend = trends[0]
        trend_type = primary_trend["Trend Type"]
        magnitude = primary_trend["Magnitude"]

        # Generate concise summary
        summary = (
            f"Primary {trend_type.lower()} with ${magnitude:.0f} magnitude detected. "
        )

        if len(trends) > 1:
            summary += f"Multiple trends identified ({len(trends)} total). "

        if (
            "golden"
            in str(
                self.level_calculator.calculate_golden_pressure_zone(primary_trend)
            ).lower()
        ):
            summary += "Golden ratio pressure zone active."

        # Generate key insights
        insights = [
            f"Strongest trend: {trend_type} (${magnitude:.0f} range)",
            f"Current price: ${current_price:.2f}",
            f"Key Fibonacci levels: {', '.join([f'{level.percentage}' for level in fibonacci_levels if level.is_key_level])}",
        ]

        if len(trends) >= 2:
            insights.append(
                f"Multiple timeframe confirmation with {len(trends)} significant trends"
            )

        return summary, insights

    def _build_raw_data(
        self, stock_data: pd.DataFrame, top_trends: list[dict[str, Any]], timeframe: str
    ) -> dict[str, Any]:
        """Build comprehensive raw data for debugging and agent use."""
        # Handle None config case
        if self.config is None:
            swing_lookback = 3
            min_magnitude_pct = 0.05
        else:
            swing_lookback = self.config.swing_lookback
            min_magnitude_pct = self.config.min_magnitude_pct

        # Calculate actual min_magnitude from percentage
        median_price = stock_data["Close"].median()
        min_magnitude = median_price * min_magnitude_pct

        return {
            "timeframe": timeframe,
            "data_points": len(stock_data),
            "date_range": {
                "start": stock_data.index[0].strftime("%Y-%m-%d"),
                "end": stock_data.index[-1].strftime("%Y-%m-%d"),
            },
            "price_range": {
                "high": float(stock_data["High"].max()),
                "low": float(stock_data["Low"].min()),
                "median": float(median_price),
            },
            "trend_detection_params": {
                "lookback": swing_lookback,
                "tolerance_pct": 3.0,
                "min_magnitude_pct": min_magnitude_pct * 100,  # Show as percentage
                "min_magnitude_absolute": float(min_magnitude),
            },
            "top_trends": [
                {
                    "rank": i + 1,
                    "type": trend["Trend Type"],
                    "period": f"{trend['Start Date']} to {trend['End Date']}",
                    "magnitude": trend["Magnitude"],
                    "high": trend["Absolute High"],
                    "low": trend["Absolute Low"],
                    "fibonacci_levels": self.level_calculator.get_fibonacci_levels_for_trend(
                        trend
                    ),
                }
                for i, trend in enumerate(top_trends[:3])
            ],
            "pressure_zones": [
                self.level_calculator.calculate_golden_pressure_zone(trend)
                for trend in top_trends[:3]
            ],
            "calculation_method": "advanced_multi_trend_detection",
        }
