"""
Fibonacci level calculation and pressure zone analysis.
Handles computation of retracement levels, key ratios, and golden pressure zones.
"""

from typing import Any, Literal

import structlog

from ....api.models import FibonacciLevel, MarketStructure, PricePoint
from .config import FibonacciConstants

logger = structlog.get_logger()


class LevelCalculator:
    """Calculates Fibonacci retracement levels and pressure zones."""

    def __init__(self) -> None:
        """Initialize calculator with standard Fibonacci constants."""
        self.constants = FibonacciConstants()

    def calculate_fibonacci_levels(self, trend: dict[str, Any]) -> list[FibonacciLevel]:
        """Calculate Fibonacci retracement levels for a given trend."""
        try:
            high_price = trend["Absolute High"]
            low_price = trend["Absolute Low"]
            price_range = high_price - low_price
            is_uptrend = "Uptrend" in trend["Trend Type"]

            fibonacci_levels = []

            for level in self.constants.FIBONACCI_LEVELS:
                if is_uptrend:
                    # For uptrends, retracements are levels below the high
                    fib_price = high_price - (price_range * level)
                else:
                    # For downtrends, retracements are levels above the low
                    fib_price = low_price + (price_range * level)

                fibonacci_levels.append(
                    FibonacciLevel(
                        level=level,
                        price=fib_price,
                        percentage=f"{level * 100:.1f}%",
                        is_key_level=level in self.constants.KEY_LEVELS,
                    )
                )

            logger.info(
                "Calculated Fibonacci levels",
                trend_type=trend["Trend Type"],
                levels_count=len(fibonacci_levels),
                key_levels_count=len(
                    [level for level in fibonacci_levels if level.is_key_level]
                ),
            )
            return fibonacci_levels

        except Exception as e:
            logger.error(
                "Failed to calculate Fibonacci levels", trend=trend, error=str(e)
            )
            return []

    def get_fibonacci_levels_for_trend(
        self, trend: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Get Fibonacci levels for a trend in dictionary format."""
        try:
            logger.info(
                f"Calculating Fibonacci levels for trend: {trend.get('Trend Type', 'Unknown')}"
            )
            logger.info(f"Trend fields: {list(trend.keys())}")
            logger.info(
                f"High: {trend.get('Absolute High')}, Low: {trend.get('Absolute Low')}"
            )

            fib_levels = self.calculate_fibonacci_levels(trend)

            result = [
                {
                    "level": level.level,
                    "price": level.price,
                    "percentage": level.percentage,
                    "is_key_level": level.is_key_level,
                }
                for level in fib_levels
            ]

            logger.info(f"Successfully calculated {len(result)} Fibonacci levels")
            return result

        except Exception as e:
            logger.error(f"Error in get_fibonacci_levels_for_trend: {str(e)}")
            logger.error(f"Trend data: {trend}")
            return []

    def calculate_golden_pressure_zone(self, trend: dict[str, Any]) -> dict[str, float]:
        """Calculate the golden ratio pressure zone (61.5% - 61.8%)."""
        high_price = trend["Absolute High"]
        low_price = trend["Absolute Low"]
        price_range = high_price - low_price
        is_uptrend = "Uptrend" in trend["Trend Type"]

        if is_uptrend:
            # For uptrends, golden zone is below the high
            upper_level = high_price - (
                price_range * self.constants.GOLDEN_ZONE_START
            )  # 61.5%
            lower_level = high_price - (
                price_range * self.constants.GOLDEN_ZONE_END
            )  # 61.8%
        else:
            # For downtrends, golden zone is above the low
            lower_level = low_price + (
                price_range * self.constants.GOLDEN_ZONE_START
            )  # 61.5%
            upper_level = low_price + (
                price_range * self.constants.GOLDEN_ZONE_END
            )  # 61.8%

        return {
            "upper_bound": max(upper_level, lower_level),  # Ensure upper > lower
            "lower_bound": min(upper_level, lower_level),
            "strength": 0.9,  # Golden zone is always high strength (0.9/1.0)
            "zone_width": abs(upper_level - lower_level),
        }

    def create_market_structure(
        self, primary_trend: dict[str, Any], current_price: float
    ) -> MarketStructure:
        """Create market structure analysis from primary trend."""
        trend_direction: Literal["uptrend", "downtrend", "sideways"] = (
            "uptrend" if "Uptrend" in primary_trend["Trend Type"] else "downtrend"
        )

        # Assess structure quality based on magnitude and price
        magnitude = primary_trend["Magnitude"]
        magnitude_pct = (magnitude / current_price) * 100

        structure_quality: Literal["high", "medium", "low"]
        if magnitude_pct > 20:
            structure_quality = "high"
        elif magnitude_pct > 10:
            structure_quality = "medium"
        else:
            structure_quality = "low"

        # Determine current market phase
        high_price = primary_trend["Absolute High"]
        low_price = primary_trend["Absolute Low"]
        price_range = high_price - low_price
        position_in_range = (
            (current_price - low_price) / price_range if price_range > 0 else 0.5
        )

        if position_in_range > 0.8:
            phase = "Near swing high - potential resistance"
        elif position_in_range < 0.2:
            phase = "Near swing low - potential support"
        elif 0.35 <= position_in_range <= 0.65:
            phase = "Middle range - watch for direction"
        else:
            phase = "In retracement zone"

        return MarketStructure(
            trend_direction=trend_direction,
            swing_high=PricePoint(
                price=high_price,
                date=str(
                    primary_trend["End Date"]
                    if "Uptrend" in primary_trend["Trend Type"]
                    else primary_trend["Start Date"]
                ),
            ),
            swing_low=PricePoint(
                price=low_price,
                date=str(
                    primary_trend["Start Date"]
                    if "Uptrend" in primary_trend["Trend Type"]
                    else primary_trend["End Date"]
                ),
            ),
            structure_quality=structure_quality,
            phase=phase,
        )

    def calculate_confidence_score(
        self, trends: list[dict[str, Any]], current_price: float
    ) -> float:
        """Calculate confidence score based on trend analysis quality."""
        if not trends:
            return 0.1

        primary_trend = trends[0]
        magnitude = primary_trend["Magnitude"]
        magnitude_pct = (magnitude / current_price) * 100

        # Base confidence from trend magnitude
        base_confidence = min(magnitude_pct / 40, 0.8)  # Cap at 80% from magnitude

        # Boost confidence if multiple significant trends detected
        if len(trends) >= 3:
            trend_diversity_bonus = 0.2
        elif len(trends) >= 2:
            trend_diversity_bonus = 0.1
        else:
            trend_diversity_bonus = 0.0

        # Final confidence capped at 95%
        final_confidence: float = min(base_confidence + trend_diversity_bonus, 0.95)

        return max(final_confidence, 0.1)  # Minimum 10% confidence

    def assess_trend_strength(self, trends: list[dict[str, Any]]) -> str:
        """Assess overall trend strength from detected trends."""
        if not trends:
            return "weak"

        primary_trend = trends[0]
        magnitude = primary_trend.get("Magnitude", 0)

        # Count trends of same direction
        uptrends = sum(1 for t in trends[:3] if "Uptrend" in t.get("Trend Type", ""))
        downtrends = sum(
            1 for t in trends[:3] if "Downtrend" in t.get("Trend Type", "")
        )

        # Assess based on magnitude and consistency
        if magnitude > 50 and max(uptrends, downtrends) >= 2:
            return "strong"
        elif magnitude > 25 or max(uptrends, downtrends) >= 2:
            return "moderate"
        else:
            return "weak"
