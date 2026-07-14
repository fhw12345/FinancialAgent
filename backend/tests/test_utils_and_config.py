"""
Comprehensive utility and configuration tests.

Tests centralized utilities and configuration logic:
- yfinance interval mapping utilities (centralized to avoid duplication)
- Timeframe configuration validation
- Symbol validation utilities
- Error handling utilities
- Cache key generation

These tests ensure robust utility functions and prevent configuration errors.
"""

import pytest

from src.core.analysis.fibonacci.config import (
    FibonacciConstants,
    TimeframeConfig,
    TimeframeConfigs,
)
from src.core.utils.yfinance_utils import (
    get_valid_frontend_intervals,
    map_timeframe_to_yfinance_interval,
)


class TestYfinanceUtilities:
    """
    REGRESSION TESTS: Centralized yfinance utilities.

    Root Cause: Duplicate mapping logic in multiple files caused inconsistencies
    Fix: Centralized all yfinance mapping logic in utils module
    """

    def test_centralized_interval_mapping_consistency(self):
        """
        CRITICAL TEST: Ensure centralized mapping prevents duplication bugs.

        Bug: Same mapping logic was duplicated in fibonacci_analyzer.py and market_data.py
        Fix: Single source of truth in yfinance_utils.py
        """
        # Test all critical mappings that caused production issues
        critical_mappings = [
            ("1w", "1wk"),  # Weekly mapping that caused API failures
            ("1M", "1mo"),  # Monthly mapping (alternative format)
            ("1mo", "1mo"),  # Monthly mapping (yfinance format)
            ("1d", "1d"),  # Daily (should pass through)
            ("1h", "1h"),  # Hourly (should pass through)
        ]

        for frontend_interval, expected_yfinance_interval in critical_mappings:
            result = map_timeframe_to_yfinance_interval(frontend_interval)
            assert result == expected_yfinance_interval, (
                f"Centralized mapping failed: '{frontend_interval}' → '{result}', "
                f"expected '{expected_yfinance_interval}'"
            )

    def test_interval_validation_lists_consistency(self):
        """Test that validation lists are consistent and comprehensive."""
        frontend_intervals = get_valid_frontend_intervals()

        # Test that key intervals are included
        required_frontend = ["1m", "1h", "1d", "1w", "1M", "1mo"]
        for interval in required_frontend:
            assert (
                interval in frontend_intervals
            ), f"Required frontend interval '{interval}' missing from validation list"

        # Test that all frontend intervals can be mapped
        for frontend_interval in frontend_intervals:
            mapped_interval = map_timeframe_to_yfinance_interval(frontend_interval)
            # Mapped interval should be valid (non-empty)
            assert (
                mapped_interval
            ), f"Frontend interval '{frontend_interval}' mapping returned empty value"

    def test_no_duplicate_mapping_logic_exists(self):
        """
        META TEST: Ensure no duplicate mapping logic exists in codebase.

        This test would ideally scan the codebase for duplicate mapping patterns.
        For now, we test that the centralized utility is the authoritative source.
        """
        # Test that our centralized mapping handles all known cases
        test_cases = [
            # Format: (input, expected_output, description)
            ("1w", "1wk", "Weekly interval conversion"),
            ("1M", "1mo", "Monthly interval conversion (alternative)"),
            ("1mo", "1mo", "Monthly interval (already compatible)"),
            ("1d", "1d", "Daily interval (pass-through)"),
            ("1h", "1h", "Hourly interval (pass-through)"),
            ("3mo", "3mo", "Quarterly interval (pass-through)"),
        ]

        for input_val, expected, description in test_cases:
            result = map_timeframe_to_yfinance_interval(input_val)
            assert (
                result == expected
            ), f"Failed {description}: {input_val} → {result}, expected {expected}"


class TestTimeframeConfiguration:
    """Test timeframe configuration validation and consistency."""

    def test_timeframe_config_completeness(self):
        """Test that all required timeframes have configurations."""
        required_timeframes = ["1h", "1d", "1w", "1M"]

        for timeframe in required_timeframes:
            config = TimeframeConfigs.get_config(timeframe)
            assert (
                config is not None
            ), f"Missing configuration for timeframe '{timeframe}'"
            assert isinstance(
                config, TimeframeConfig
            ), f"Configuration for '{timeframe}' should be TimeframeConfig instance"

    def test_timeframe_config_parameter_validation(self):
        """Test that timeframe configuration parameters are reasonable."""
        for timeframe, config in TimeframeConfigs.CONFIGS.items():
            # Test that all parameters are positive
            assert (
                config.swing_lookback > 0
            ), f"Timeframe '{timeframe}' swing_lookback must be positive"
            assert (
                config.prominence > 0
            ), f"Timeframe '{timeframe}' prominence must be positive"
            assert (
                config.min_magnitude_pct > 0
            ), f"Timeframe '{timeframe}' min_magnitude_pct must be positive"
            assert (
                config.tolerance_pct > 0
            ), f"Timeframe '{timeframe}' tolerance_pct must be positive"

            # Test reasonable ranges
            assert (
                1 <= config.swing_lookback <= 20
            ), f"Timeframe '{timeframe}' swing_lookback should be reasonable (1-20)"
            assert (
                0.1 <= config.prominence <= 10
            ), f"Timeframe '{timeframe}' prominence should be reasonable (0.1-10)"
            assert (
                0.001 <= config.tolerance_pct <= 0.05
            ), f"Timeframe '{timeframe}' tolerance_pct should be reasonable (0.1%-5%)"

    def test_timeframe_config_scaling_logic(self):
        """Test that longer timeframes have appropriately scaled parameters."""
        daily_config = TimeframeConfigs.get_config("1d")
        _weekly_config = TimeframeConfigs.get_config("1w")
        monthly_config = TimeframeConfigs.get_config("1M")

        # Monthly should have parameters scaled for longer timeframes
        assert (
            monthly_config.prominence >= daily_config.prominence
        ), "Monthly prominence should be >= daily for longer timeframe scaling"

    def test_default_timeframe_fallback(self):
        """Test that unknown timeframes fall back to daily configuration."""
        unknown_timeframe = "unknown"
        config = TimeframeConfigs.get_config(unknown_timeframe)
        daily_config = TimeframeConfigs.get_config("1d")

        # Should return daily config as fallback
        assert (
            config == daily_config
        ), f"Unknown timeframe '{unknown_timeframe}' should fallback to daily config"


class TestFibonacciConstants:
    """Test Fibonacci constants and validation."""

    def test_fibonacci_levels_completeness(self):
        """Test that all expected Fibonacci levels are present."""
        levels = FibonacciConstants.FIBONACCI_LEVELS

        # Test essential Fibonacci levels are present
        essential_levels = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
        for level in essential_levels:
            assert level in levels, f"Essential Fibonacci level {level} missing"

        # Test levels are sorted
        assert levels == sorted(levels), "Fibonacci levels should be sorted"

        # Test levels are in valid range
        for level in levels:
            assert 0 <= level <= 1, f"Fibonacci level {level} should be between 0 and 1"

    def test_key_levels_validation(self):
        """Test that key levels are subset of all levels."""
        all_levels = FibonacciConstants.FIBONACCI_LEVELS
        key_levels = FibonacciConstants.KEY_LEVELS

        for key_level in key_levels:
            assert (
                key_level in all_levels
            ), f"Key level {key_level} must be in the main Fibonacci levels list"

        # Test that we have reasonable number of key levels
        assert (
            2 <= len(key_levels) <= 5
        ), f"Should have 2-5 key levels, got {len(key_levels)}"

    def test_golden_ratio_constants(self):
        """Test golden ratio and zone constants."""
        # Test golden ratio value
        assert (
            abs(FibonacciConstants.GOLDEN_RATIO - 0.618) < 0.001
        ), "Golden ratio should be approximately 0.618"

        # Test golden zone boundaries
        assert (
            FibonacciConstants.GOLDEN_ZONE_START < FibonacciConstants.GOLDEN_ZONE_END
        ), "Golden zone start should be less than end"

        # Test golden zone is around the golden ratio
        golden_ratio = FibonacciConstants.GOLDEN_RATIO
        zone_start = FibonacciConstants.GOLDEN_ZONE_START
        zone_end = FibonacciConstants.GOLDEN_ZONE_END

        assert (
            zone_start <= golden_ratio <= zone_end
        ), f"Golden ratio {golden_ratio} should be within zone [{zone_start}, {zone_end}]"


class TestConfigurationIntegration:
    """Test integration between different configuration components."""

    def test_timeframe_config_interval_consistency(self):
        """Test that timeframe config intervals match yfinance utils."""
        # Get all configured timeframes
        configured_timeframes = list(TimeframeConfigs.CONFIGS.keys())

        for timeframe in configured_timeframes:
            # Test that each configured timeframe can be mapped by yfinance utils
            mapped_interval = map_timeframe_to_yfinance_interval(timeframe)

            # Mapped interval should be valid (non-empty)
            assert (
                mapped_interval
            ), f"Timeframe '{timeframe}' mapping returned empty value"

    def test_fibonacci_config_level_consistency(self):
        """Test consistency between Fibonacci constants and level calculations."""
        levels = FibonacciConstants.FIBONACCI_LEVELS
        key_levels = FibonacciConstants.KEY_LEVELS

        # Test that golden ratio is in the levels list
        golden_ratio = FibonacciConstants.GOLDEN_RATIO
        assert (
            golden_ratio in levels
        ), f"Golden ratio {golden_ratio} should be in Fibonacci levels"

        # Test that golden ratio is a key level
        assert (
            golden_ratio in key_levels
        ), f"Golden ratio {golden_ratio} should be a key level"

        # Test that all key levels are actually important Fibonacci numbers
        important_levels = [0.236, 0.382, 0.5, 0.618, 0.786]
        for key_level in key_levels:
            assert (
                key_level in important_levels
            ), f"Key level {key_level} should be an important Fibonacci number"


class TestErrorHandlingUtilities:
    """Test error handling and validation utilities."""

    def test_configuration_error_handling(self):
        """Test that configuration errors are handled gracefully."""
        # Test getting config for invalid timeframe
        invalid_config = TimeframeConfigs.get_config("invalid_timeframe")
        default_config = TimeframeConfigs.get_config("1d")

        assert (
            invalid_config == default_config
        ), "Invalid timeframe should return default (daily) configuration"

    def test_utility_function_error_handling(self):
        """Test that utility functions handle errors gracefully."""
        # Test mapping with invalid input types
        test_cases = [
            (123, "123"),  # Integer input
            (1.5, "1.5"),  # Float input
        ]

        for input_val, expected_str in test_cases:
            try:
                result = map_timeframe_to_yfinance_interval(str(input_val))
                assert (
                    result == expected_str
                ), f"Should handle string conversion: {input_val} → {result}"
            except Exception as e:
                pytest.fail(
                    f"Utility function should handle type conversion gracefully: {e}"
                )

    def test_validation_list_completeness(self):
        """Test that validation lists are complete and don't have gaps."""
        frontend_intervals = get_valid_frontend_intervals()

        # Test no duplicates
        assert len(frontend_intervals) == len(
            set(frontend_intervals)
        ), "Frontend intervals should not have duplicates"

        # Test reasonable list sizes
        assert (
            5 <= len(frontend_intervals) <= 20
        ), f"Frontend intervals list seems unreasonable size: {len(frontend_intervals)}"
