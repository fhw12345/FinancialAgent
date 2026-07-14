"""
Unit tests for Fibonacci level calculator.

Tests Fibonacci retracement calculation including:
- Level calculation for uptrends and downtrends
- Golden pressure zone calculation
- Market structure analysis
- Confidence scoring
- Trend strength assessment
"""

import pytest

from src.core.analysis.fibonacci.level_calculator import LevelCalculator

# ===== Fixtures =====


@pytest.fixture
def calculator():
    """Fibonacci level calculator instance"""
    return LevelCalculator()


@pytest.fixture
def uptrend_data():
    """Sample uptrend trend data"""
    return {
        "Trend Type": "Uptrend",
        "Absolute High": 150.0,
        "Absolute Low": 100.0,
        "Magnitude": 50.0,
        "Start Date": "2025-01-01",
        "End Date": "2025-01-10",
    }


@pytest.fixture
def downtrend_data():
    """Sample downtrend trend data"""
    return {
        "Trend Type": "Downtrend",
        "Absolute High": 200.0,
        "Absolute Low": 150.0,
        "Magnitude": 50.0,
        "Start Date": "2025-01-01",
        "End Date": "2025-01-10",
    }


# ===== Fibonacci Level Calculation Tests =====


class TestCalculateFibonacciLevels:
    """Test Fibonacci retracement level calculation"""

    def test_calculate_uptrend_levels(self, calculator, uptrend_data):
        """Test calculation of Fibonacci levels for uptrend"""
        # Act
        levels = calculator.calculate_fibonacci_levels(uptrend_data)

        # Assert
        assert len(levels) == 8  # 8 standard Fibonacci levels
        assert all(hasattr(level, "level") for level in levels)
        assert all(hasattr(level, "price") for level in levels)
        assert all(hasattr(level, "percentage") for level in levels)
        assert all(hasattr(level, "is_key_level") for level in levels)

    def test_uptrend_0_level_at_high(self, calculator, uptrend_data):
        """Test that 0% level is at the high for uptrends"""
        # Act
        levels = calculator.calculate_fibonacci_levels(uptrend_data)

        # Assert
        level_0 = next(level for level in levels if level.level == 0.0)
        assert level_0.price == 150.0  # Should be at the high

    def test_uptrend_100_level_at_low(self, calculator, uptrend_data):
        """Test that 100% level is at the low for uptrends"""
        # Act
        levels = calculator.calculate_fibonacci_levels(uptrend_data)

        # Assert
        level_100 = next(level for level in levels if level.level == 1.0)
        assert level_100.price == 100.0  # Should be at the low

    def test_uptrend_618_golden_ratio(self, calculator, uptrend_data):
        """Test 61.8% golden ratio level for uptrend"""
        # Act
        levels = calculator.calculate_fibonacci_levels(uptrend_data)

        # Assert
        # High = 150, Low = 100, Range = 50
        # 61.8% retracement = 150 - (50 * 0.618) = 150 - 30.9 = 119.1
        level_618 = next(level for level in levels if level.level == 0.618)
        assert level_618.price == pytest.approx(119.1, abs=0.1)
        assert level_618.is_key_level is True

    def test_uptrend_50_percent_level(self, calculator, uptrend_data):
        """Test 50% retracement level for uptrend"""
        # Act
        levels = calculator.calculate_fibonacci_levels(uptrend_data)

        # Assert
        # 50% = 150 - (50 * 0.5) = 125
        level_50 = next(level for level in levels if level.level == 0.5)
        assert level_50.price == 125.0
        assert level_50.is_key_level is True

    def test_uptrend_382_level(self, calculator, uptrend_data):
        """Test 38.2% level for uptrend"""
        # Act
        levels = calculator.calculate_fibonacci_levels(uptrend_data)

        # Assert
        # 38.2% = 150 - (50 * 0.382) = 150 - 19.1 = 130.9
        level_382 = next(level for level in levels if level.level == 0.382)
        assert level_382.price == pytest.approx(130.9, abs=0.1)
        assert level_382.is_key_level is True

    def test_downtrend_0_level_at_low(self, calculator, downtrend_data):
        """Test that 0% level is at the low for downtrends"""
        # Act
        levels = calculator.calculate_fibonacci_levels(downtrend_data)

        # Assert
        level_0 = next(level for level in levels if level.level == 0.0)
        assert level_0.price == 150.0  # Should be at the low

    def test_downtrend_100_level_at_high(self, calculator, downtrend_data):
        """Test that 100% level is at the high for downtrends"""
        # Act
        levels = calculator.calculate_fibonacci_levels(downtrend_data)

        # Assert
        level_100 = next(level for level in levels if level.level == 1.0)
        assert level_100.price == 200.0  # Should be at the high

    def test_downtrend_618_golden_ratio(self, calculator, downtrend_data):
        """Test 61.8% golden ratio level for downtrend"""
        # Act
        levels = calculator.calculate_fibonacci_levels(downtrend_data)

        # Assert
        # High = 200, Low = 150, Range = 50
        # 61.8% retracement = 150 + (50 * 0.618) = 150 + 30.9 = 180.9
        level_618 = next(level for level in levels if level.level == 0.618)
        assert level_618.price == pytest.approx(180.9, abs=0.1)

    def test_key_levels_marked_correctly(self, calculator, uptrend_data):
        """Test that key levels (38.2%, 50%, 61.8%) are marked"""
        # Act
        levels = calculator.calculate_fibonacci_levels(uptrend_data)

        # Assert
        key_levels = [level for level in levels if level.is_key_level]
        assert len(key_levels) == 3
        key_level_values = [level.level for level in key_levels]
        assert 0.382 in key_level_values
        assert 0.5 in key_level_values
        assert 0.618 in key_level_values

    def test_percentage_format(self, calculator, uptrend_data):
        """Test that percentage strings are formatted correctly"""
        # Act
        levels = calculator.calculate_fibonacci_levels(uptrend_data)

        # Assert
        level_618 = next(level for level in levels if level.level == 0.618)
        assert level_618.percentage == "61.8%"

        level_50 = next(level for level in levels if level.level == 0.5)
        assert level_50.percentage == "50.0%"

    def test_get_fibonacci_levels_for_trend_dict_format(self, calculator, uptrend_data):
        """Test dictionary format output"""
        # Act
        levels = calculator.get_fibonacci_levels_for_trend(uptrend_data)

        # Assert
        assert isinstance(levels, list)
        assert len(levels) == 8
        assert all(isinstance(level, dict) for level in levels)
        assert all("level" in level for level in levels)
        assert all("price" in level for level in levels)
        assert all("percentage" in level for level in levels)
        assert all("is_key_level" in level for level in levels)

    def test_calculate_levels_handles_errors(self, calculator):
        """Test error handling for invalid trend data"""
        # Arrange
        invalid_trend = {"Trend Type": "Uptrend"}  # Missing required fields

        # Act
        levels = calculator.calculate_fibonacci_levels(invalid_trend)

        # Assert - should return empty list on error
        assert levels == []


# ===== Golden Pressure Zone Tests =====


class TestCalculateGoldenPressureZone:
    """Test golden ratio pressure zone calculation"""

    def test_uptrend_golden_zone(self, calculator, uptrend_data):
        """Test golden zone for uptrend"""
        # Act
        zone = calculator.calculate_golden_pressure_zone(uptrend_data)

        # Assert
        # High = 150, Low = 100, Range = 50
        # 61.5% = 150 - (50 * 0.615) = 119.25
        # 61.8% = 150 - (50 * 0.618) = 119.10
        assert zone["upper_bound"] == pytest.approx(119.25, abs=0.1)
        assert zone["lower_bound"] == pytest.approx(119.10, abs=0.1)
        assert zone["strength"] == 0.9
        assert zone["zone_width"] == pytest.approx(0.15, abs=0.01)

    def test_downtrend_golden_zone(self, calculator, downtrend_data):
        """Test golden zone for downtrend"""
        # Act
        zone = calculator.calculate_golden_pressure_zone(downtrend_data)

        # Assert
        # High = 200, Low = 150, Range = 50
        # 61.5% = 150 + (50 * 0.615) = 180.75
        # 61.8% = 150 + (50 * 0.618) = 180.90
        assert zone["lower_bound"] == pytest.approx(180.75, abs=0.1)
        assert zone["upper_bound"] == pytest.approx(180.90, abs=0.1)
        assert zone["strength"] == 0.9

    def test_golden_zone_upper_always_greater_than_lower(
        self, calculator, uptrend_data
    ):
        """Test that upper bound is always greater than lower bound"""
        # Act
        zone = calculator.calculate_golden_pressure_zone(uptrend_data)

        # Assert
        assert zone["upper_bound"] > zone["lower_bound"]

    def test_golden_zone_zone_width_calculation(self, calculator, uptrend_data):
        """Test zone width is absolute difference"""
        # Act
        zone = calculator.calculate_golden_pressure_zone(uptrend_data)

        # Assert
        expected_width = abs(zone["upper_bound"] - zone["lower_bound"])
        assert zone["zone_width"] == pytest.approx(expected_width, abs=0.001)


# ===== Market Structure Tests =====


class TestCreateMarketStructure:
    """Test market structure analysis"""

    def test_uptrend_market_structure(self, calculator, uptrend_data):
        """Test market structure for uptrend"""
        # Arrange
        current_price = 140.0

        # Act
        structure = calculator.create_market_structure(uptrend_data, current_price)

        # Assert
        assert structure.trend_direction == "uptrend"
        assert structure.swing_high.price == 150.0
        assert structure.swing_low.price == 100.0
        assert structure.swing_high.date == "2025-01-10"  # End date for uptrend
        assert structure.swing_low.date == "2025-01-01"  # Start date for uptrend

    def test_downtrend_market_structure(self, calculator, downtrend_data):
        """Test market structure for downtrend"""
        # Arrange
        current_price = 170.0

        # Act
        structure = calculator.create_market_structure(downtrend_data, current_price)

        # Assert
        assert structure.trend_direction == "downtrend"
        assert structure.swing_high.price == 200.0
        assert structure.swing_low.price == 150.0
        assert structure.swing_high.date == "2025-01-01"  # Start date for downtrend
        assert structure.swing_low.date == "2025-01-10"  # End date for downtrend

    def test_structure_quality_high(self, calculator, uptrend_data):
        """Test high structure quality (magnitude > 20% of price)"""
        # Arrange
        current_price = 200.0  # Magnitude 50 / 200 = 25% > 20%

        # Act
        structure = calculator.create_market_structure(uptrend_data, current_price)

        # Assert
        assert structure.structure_quality == "high"

    def test_structure_quality_medium(self, calculator, uptrend_data):
        """Test medium structure quality (10% < magnitude < 20%)"""
        # Arrange
        current_price = 400.0  # Magnitude 50 / 400 = 12.5% (10-20%)

        # Act
        structure = calculator.create_market_structure(uptrend_data, current_price)

        # Assert
        assert structure.structure_quality == "medium"

    def test_structure_quality_low(self, calculator, uptrend_data):
        """Test low structure quality (magnitude < 10%)"""
        # Arrange
        current_price = 600.0  # Magnitude 50 / 600 = 8.3% < 10%

        # Act
        structure = calculator.create_market_structure(uptrend_data, current_price)

        # Assert
        assert structure.structure_quality == "low"

    def test_phase_near_swing_high(self, calculator, uptrend_data):
        """Test phase detection near swing high"""
        # Arrange
        current_price = 148.0  # (148-100)/(150-100) = 96% > 80%

        # Act
        structure = calculator.create_market_structure(uptrend_data, current_price)

        # Assert
        assert structure.phase == "Near swing high - potential resistance"

    def test_phase_near_swing_low(self, calculator, uptrend_data):
        """Test phase detection near swing low"""
        # Arrange
        current_price = 105.0  # (105-100)/(150-100) = 10% < 20%

        # Act
        structure = calculator.create_market_structure(uptrend_data, current_price)

        # Assert
        assert structure.phase == "Near swing low - potential support"

    def test_phase_middle_range(self, calculator, uptrend_data):
        """Test phase detection in middle range"""
        # Arrange
        current_price = 125.0  # (125-100)/(150-100) = 50% (in 35-65% range)

        # Act
        structure = calculator.create_market_structure(uptrend_data, current_price)

        # Assert
        assert structure.phase == "Middle range - watch for direction"

    def test_phase_retracement_zone(self, calculator, uptrend_data):
        """Test phase detection in retracement zone"""
        # Arrange
        current_price = 135.0  # (135-100)/(150-100) = 70% (not in other zones)

        # Act
        structure = calculator.create_market_structure(uptrend_data, current_price)

        # Assert
        assert structure.phase == "In retracement zone"


# ===== Confidence Score Tests =====


class TestCalculateConfidenceScore:
    """Test confidence score calculation"""

    def test_confidence_empty_trends(self, calculator):
        """Test confidence with no trends"""
        # Act
        confidence = calculator.calculate_confidence_score([], 150.0)

        # Assert
        assert confidence == 0.1  # Minimum confidence

    def test_confidence_single_large_trend(self, calculator, uptrend_data):
        """Test confidence with single large trend"""
        # Arrange
        current_price = 100.0  # Magnitude 50 / 100 = 50% > 40%

        # Act
        confidence = calculator.calculate_confidence_score(
            [uptrend_data], current_price
        )

        # Assert
        # Base: min(50/40, 0.8) = 0.8
        # No diversity bonus (single trend)
        # Final: max(0.8, 0.1) = 0.8
        assert confidence == pytest.approx(0.8, abs=0.01)

    def test_confidence_with_trend_diversity_bonus(self, calculator, uptrend_data):
        """Test confidence boost from multiple trends"""
        # Arrange
        current_price = 100.0
        trends = [uptrend_data, uptrend_data, uptrend_data]  # 3 trends

        # Act
        confidence = calculator.calculate_confidence_score(trends, current_price)

        # Assert
        # Base: 0.8 (from magnitude)
        # Diversity bonus: 0.2 (3 trends)
        # Final: min(0.8 + 0.2, 0.95) = 0.95 (capped)
        assert confidence == pytest.approx(0.95, abs=0.01)

    def test_confidence_capped_at_95_percent(self, calculator):
        """Test that confidence is capped at 95%"""
        # Arrange - very large trend
        large_trend = {
            "Magnitude": 100.0,
            "Trend Type": "Uptrend",
            "Absolute High": 200.0,
            "Absolute Low": 100.0,
        }
        current_price = 50.0  # Magnitude 100 / 50 = 200%
        trends = [large_trend, large_trend, large_trend]

        # Act
        confidence = calculator.calculate_confidence_score(trends, current_price)

        # Assert
        assert confidence <= 0.95

    def test_confidence_minimum_10_percent(self, calculator):
        """Test that confidence has minimum of 10%"""
        # Arrange - very small trend
        small_trend = {
            "Magnitude": 1.0,
            "Trend Type": "Uptrend",
            "Absolute High": 101.0,
            "Absolute Low": 100.0,
        }
        current_price = 1000.0  # Magnitude 1 / 1000 = 0.1%

        # Act
        confidence = calculator.calculate_confidence_score([small_trend], current_price)

        # Assert
        assert confidence >= 0.1


# ===== Trend Strength Assessment Tests =====


class TestAssessTrendStrength:
    """Test trend strength assessment"""

    def test_strength_no_trends(self, calculator):
        """Test strength assessment with no trends"""
        # Act
        strength = calculator.assess_trend_strength([])

        # Assert
        assert strength == "weak"

    def test_strength_strong_large_magnitude_consistent(self, calculator):
        """Test strong trend (large magnitude + consistency)"""
        # Arrange
        strong_uptrend = {
            "Magnitude": 60.0,
            "Trend Type": "Uptrend",
        }
        trends = [strong_uptrend, strong_uptrend, strong_uptrend]

        # Act
        strength = calculator.assess_trend_strength(trends)

        # Assert
        # Magnitude > 50 and 3 uptrends >= 2
        assert strength == "strong"

    def test_strength_moderate_medium_magnitude(self, calculator):
        """Test moderate trend"""
        # Arrange
        moderate_trend = {
            "Magnitude": 30.0,
            "Trend Type": "Uptrend",
        }

        # Act
        strength = calculator.assess_trend_strength([moderate_trend])

        # Assert
        # Magnitude 30 > 25
        assert strength == "moderate"

    def test_strength_moderate_consistent_direction(self, calculator):
        """Test moderate trend from consistency"""
        # Arrange
        uptrend1 = {"Magnitude": 20.0, "Trend Type": "Uptrend"}
        uptrend2 = {"Magnitude": 15.0, "Trend Type": "Uptrend"}

        # Act
        strength = calculator.assess_trend_strength([uptrend1, uptrend2])

        # Assert
        # Magnitude < 25 but 2 uptrends >= 2
        assert strength == "moderate"

    def test_strength_weak_small_magnitude(self, calculator):
        """Test weak trend"""
        # Arrange
        weak_trend = {
            "Magnitude": 10.0,
            "Trend Type": "Uptrend",
        }

        # Act
        strength = calculator.assess_trend_strength([weak_trend])

        # Assert
        assert strength == "weak"

    def test_strength_counts_only_first_three_trends(self, calculator):
        """Test that only first 3 trends are considered for consistency"""
        # Arrange
        uptrend = {"Magnitude": 20.0, "Trend Type": "Uptrend"}
        downtrend = {"Magnitude": 20.0, "Trend Type": "Downtrend"}
        # First 3 are uptrends, 4th is downtrend
        trends = [uptrend, uptrend, uptrend, downtrend]

        # Act
        strength = calculator.assess_trend_strength(trends)

        # Assert
        # Should detect 3 consistent uptrends → moderate
        assert strength == "moderate"
