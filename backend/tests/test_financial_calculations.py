"""
Comprehensive financial calculation tests.

Tests critical financial calculations that caused production bugs:
- Dividend yield calculation (41% vs 0.41% bug)
- Fibonacci level calculations
- Pressure zone calculations (string vs float validation errors)
- Trend detection algorithms
- Confidence score calculations

These tests ensure mathematical accuracy and prevent calculation errors.
"""

from datetime import date

import pytest

from src.core.analysis.fibonacci import (
    LevelCalculator,
)
from src.core.analysis.fibonacci.config import FibonacciConstants

# TestDividendYieldCalculation class removed - marked with:
# @pytest.mark.skip(reason="Requires Alpha Vantage fundamentals implementation - yfinance deprecated")
#
# The class contained ~130 lines of dividend yield calculation regression tests
# that are no longer relevant after yfinance deprecation. These tests will need
# to be rewritten when Alpha Vantage COMPANY_OVERVIEW endpoint is integrated.


class TestFibonacciCalculations:
    """Test Fibonacci level calculations and pressure zone logic."""

    @pytest.fixture
    def level_calculator(self):
        """Create LevelCalculator instance for testing."""
        return LevelCalculator()

    @pytest.fixture
    def sample_trend_data(self):
        """Sample trend data for testing calculations."""
        return {
            "Trend Type": "Uptrend",
            "Start Date": date(2024, 1, 1),
            "End Date": date(2024, 6, 1),
            "Absolute High": 200.0,
            "Absolute Low": 150.0,
            "Magnitude": 50.0,
        }

    def test_fibonacci_level_calculation_accuracy(
        self, level_calculator, sample_trend_data
    ):
        """Test mathematical accuracy of Fibonacci level calculations."""
        levels = level_calculator.calculate_fibonacci_levels(sample_trend_data)

        # Test that we get all expected levels
        expected_level_count = len(FibonacciConstants.FIBONACCI_LEVELS)
        assert (
            len(levels) == expected_level_count
        ), f"Expected {expected_level_count} Fibonacci levels, got {len(levels)}"

        # Test specific calculations for uptrend
        high_price = 200.0
        low_price = 150.0
        price_range = high_price - low_price  # 50.0

        # Verify key Fibonacci levels for uptrend (levels below high)
        level_tests = [
            (0.0, high_price - (price_range * 0.0)),  # 200.0 (no retracement)
            (0.382, high_price - (price_range * 0.382)),  # 180.9 (38.2% retracement)
            (0.5, high_price - (price_range * 0.5)),  # 175.0 (50% retracement)
            (0.618, high_price - (price_range * 0.618)),  # 169.1 (61.8% retracement)
            (1.0, high_price - (price_range * 1.0)),  # 150.0 (100% retracement)
        ]

        for expected_level, expected_price in level_tests:
            # Find the matching Fibonacci level
            matching_level = next(
                (level for level in levels if level.level == expected_level), None
            )

            assert (
                matching_level is not None
            ), f"Missing Fibonacci level {expected_level}"
            assert abs(matching_level.price - expected_price) < 0.01, (
                f"Fibonacci {expected_level} level calculation error: "
                f"expected {expected_price}, got {matching_level.price}"
            )

    def test_fibonacci_level_downtrend_calculation(self, level_calculator):
        """Test Fibonacci calculations for downtrend (levels above low)."""
        downtrend_data = {
            "Trend Type": "Downtrend",
            "Start Date": date(2024, 1, 1),
            "End Date": date(2024, 6, 1),
            "Absolute High": 200.0,
            "Absolute Low": 150.0,
            "Magnitude": 50.0,
        }

        levels = level_calculator.calculate_fibonacci_levels(downtrend_data)

        # For downtrend, levels are above the low
        low_price = 150.0
        high_price = 200.0
        price_range = high_price - low_price  # 50.0

        # Verify key Fibonacci levels for downtrend (levels above low)
        key_level_tests = [
            (0.382, low_price + (price_range * 0.382)),  # 169.1 (38.2% retracement up)
            (0.618, low_price + (price_range * 0.618)),  # 180.9 (61.8% retracement up)
        ]

        for expected_level, expected_price in key_level_tests:
            matching_level = next(
                (level for level in levels if level.level == expected_level), None
            )

            assert (
                matching_level is not None
            ), f"Missing downtrend Fibonacci level {expected_level}"
            assert abs(matching_level.price - expected_price) < 0.01, (
                f"Downtrend Fibonacci {expected_level} calculation error: "
                f"expected {expected_price}, got {matching_level.price}"
            )

    def test_key_level_identification(self, level_calculator, sample_trend_data):
        """Test that key Fibonacci levels are properly identified."""
        levels = level_calculator.calculate_fibonacci_levels(sample_trend_data)

        # Test that key levels are marked correctly
        key_levels = [level for level in levels if level.is_key_level]
        expected_key_levels = FibonacciConstants.KEY_LEVELS  # [0.382, 0.5, 0.618]

        assert len(key_levels) == len(
            expected_key_levels
        ), f"Expected {len(expected_key_levels)} key levels, got {len(key_levels)}"

        key_level_values = [level.level for level in key_levels]
        for expected_key in expected_key_levels:
            assert (
                expected_key in key_level_values
            ), f"Key level {expected_key} not marked as key level"


class TestPressureZoneCalculations:
    """
    REGRESSION TESTS: Pressure zone calculations (string vs float validation errors).

    Root Cause: Pressure zone returned strings like "high" and "golden_ratio"
    but Pydantic model expected Dict[str, float] causing validation errors.
    """

    @pytest.fixture
    def level_calculator(self):
        """Create LevelCalculator instance for testing."""
        return LevelCalculator()

    @pytest.fixture
    def uptrend_data(self):
        """Sample uptrend data for pressure zone testing."""
        return {
            "Trend Type": "Uptrend",
            "Absolute High": 200.0,
            "Absolute Low": 150.0,
        }

    @pytest.fixture
    def downtrend_data(self):
        """Sample downtrend data for pressure zone testing."""
        return {
            "Trend Type": "Downtrend",
            "Absolute High": 200.0,
            "Absolute Low": 150.0,
        }

    def test_pressure_zone_returns_only_numeric_values(
        self, level_calculator, uptrend_data
    ):
        """
        CRITICAL REGRESSION TEST: Ensure pressure zone returns only numeric values.

        Bug: Original code returned {"strength": "high", "zone_type": "golden_ratio"}
        Fix: Return {"strength": 0.9, "zone_width": float_value}
        """
        pressure_zone = level_calculator.calculate_golden_pressure_zone(uptrend_data)

        # Test that all values are numeric (required for Pydantic validation)
        for key, value in pressure_zone.items():
            assert isinstance(value, int | float), (
                f"Pressure zone key '{key}' has non-numeric value: {value} ({type(value)}). "
                f"All values must be numeric for Pydantic Dict[str, float] validation."
            )

        # Test specific required fields
        required_numeric_fields = ["upper_bound", "lower_bound", "strength"]
        for field in required_numeric_fields:
            assert field in pressure_zone, f"Missing required field: {field}"
            assert isinstance(
                pressure_zone[field], int | float
            ), f"Field '{field}' must be numeric, got {type(pressure_zone[field])}"

    def test_golden_pressure_zone_calculation_accuracy(
        self, level_calculator, uptrend_data
    ):
        """Test mathematical accuracy of golden pressure zone calculations."""
        pressure_zone = level_calculator.calculate_golden_pressure_zone(uptrend_data)

        high_price = 200.0
        low_price = 150.0
        price_range = high_price - low_price  # 50.0

        # For uptrend, golden zone is below the high
        expected_upper = high_price - (price_range * 0.615)  # 61.5% level
        expected_lower = high_price - (price_range * 0.618)  # 61.8% level

        # Test calculation accuracy
        assert abs(pressure_zone["upper_bound"] - expected_upper) < 0.01, (
            f"Golden zone upper bound calculation error: "
            f"expected {expected_upper}, got {pressure_zone['upper_bound']}"
        )

        assert abs(pressure_zone["lower_bound"] - expected_lower) < 0.01, (
            f"Golden zone lower bound calculation error: "
            f"expected {expected_lower}, got {pressure_zone['lower_bound']}"
        )

        # Test logical constraints
        assert (
            pressure_zone["upper_bound"] > pressure_zone["lower_bound"]
        ), "Golden zone upper bound must be greater than lower bound"

    def test_pressure_zone_downtrend_calculations(
        self, level_calculator, downtrend_data
    ):
        """Test pressure zone calculations for downtrend scenarios."""
        pressure_zone = level_calculator.calculate_golden_pressure_zone(downtrend_data)

        high_price = 200.0
        low_price = 150.0
        _price_range = high_price - low_price  # 50.0

        # For downtrend, golden zone is above the low (61.5%-61.8% retracement)

        # Test that bounds are correctly ordered (upper > lower)
        assert (
            pressure_zone["upper_bound"] > pressure_zone["lower_bound"]
        ), "Pressure zone upper bound must be greater than lower bound"

        # Test that values are in reasonable range
        assert (
            low_price <= pressure_zone["lower_bound"] <= high_price
        ), "Pressure zone lower bound must be within price range"
        assert (
            low_price <= pressure_zone["upper_bound"] <= high_price
        ), "Pressure zone upper bound must be within price range"

    def test_pressure_zone_strength_validation(self, level_calculator, uptrend_data):
        """Test that pressure zone strength is properly validated."""
        pressure_zone = level_calculator.calculate_golden_pressure_zone(uptrend_data)

        # Test strength field constraints
        strength = pressure_zone["strength"]
        assert isinstance(strength, int | float), "Strength must be numeric"
        assert 0 <= strength <= 1, f"Strength should be 0-1 range, got {strength}"

        # Golden zone should have high strength
        assert strength >= 0.8, f"Golden zone should have high strength, got {strength}"


class TestConfidenceScoreCalculation:
    """Test confidence score calculations for analysis quality assessment."""

    @pytest.fixture
    def level_calculator(self):
        """Create LevelCalculator instance for testing."""
        return LevelCalculator()

    def test_confidence_score_range_validation(self, level_calculator):
        """Test that confidence scores are within valid range (0-1)."""
        test_scenarios = [
            # (trends, current_price, description)
            ([], 100.0, "No trends detected"),
            ([{"Magnitude": 10}], 100.0, "Low magnitude trend"),
            ([{"Magnitude": 50}], 100.0, "Medium magnitude trend"),
            ([{"Magnitude": 100}], 100.0, "High magnitude trend"),
            (
                [{"Magnitude": 30}, {"Magnitude": 25}, {"Magnitude": 20}],
                100.0,
                "Multiple trends",
            ),
        ]

        for trends, current_price, description in test_scenarios:
            confidence = level_calculator.calculate_confidence_score(
                trends, current_price
            )

            # Test valid range
            assert (
                0 <= confidence <= 1
            ), f"Confidence score must be 0-1, got {confidence} for {description}"

            # Test minimum confidence
            assert (
                confidence >= 0.1
            ), f"Confidence should have minimum 0.1, got {confidence} for {description}"

    def test_confidence_score_magnitude_correlation(self, level_calculator):
        """Test that higher magnitude trends result in higher confidence."""
        current_price = 100.0

        # Test increasing magnitude trends
        low_magnitude_trends = [{"Magnitude": 5}]
        medium_magnitude_trends = [{"Magnitude": 25}]
        high_magnitude_trends = [{"Magnitude": 50}]

        low_confidence = level_calculator.calculate_confidence_score(
            low_magnitude_trends, current_price
        )
        medium_confidence = level_calculator.calculate_confidence_score(
            medium_magnitude_trends, current_price
        )
        high_confidence = level_calculator.calculate_confidence_score(
            high_magnitude_trends, current_price
        )

        # Confidence should increase with magnitude
        assert low_confidence < medium_confidence < high_confidence, (
            f"Confidence should increase with magnitude: "
            f"low={low_confidence}, medium={medium_confidence}, high={high_confidence}"
        )

    def test_multiple_trends_boost_confidence(self, level_calculator):
        """Test that multiple trends increase confidence score."""
        current_price = 100.0
        base_trend = {"Magnitude": 25}

        single_trend_confidence = level_calculator.calculate_confidence_score(
            [base_trend], current_price
        )

        multiple_trends_confidence = level_calculator.calculate_confidence_score(
            [base_trend, base_trend, base_trend], current_price
        )

        assert multiple_trends_confidence > single_trend_confidence, (
            f"Multiple trends should boost confidence: "
            f"single={single_trend_confidence}, multiple={multiple_trends_confidence}"
        )
