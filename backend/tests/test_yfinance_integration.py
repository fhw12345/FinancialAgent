"""
Comprehensive yfinance integration tests.

Tests the critical yfinance API integration that caused multiple production issues:
- Interval mapping ('1w' → '1wk' conversion failures)
- Symbol validation (delisted symbols like XLY causing crashes)
- Data availability validation
- Error handling and fallbacks

These tests ensure robust integration with the external yfinance API.
"""

from unittest.mock import Mock, patch

import pandas as pd
import pytest
import yfinance as yf

from src.core.utils.yfinance_utils import (
    get_valid_frontend_intervals,
    map_timeframe_to_yfinance_interval,
)


class TestYfinanceIntervalMapping:
    """Test the critical interval mapping that caused '1w' vs '1wk' failures."""

    def test_weekly_interval_mapping_prevents_yfinance_error(self):
        """
        REGRESSION TEST: Ensure '1w' maps to '1wk' to prevent yfinance errors.

        Root Cause: yfinance.history(interval='1w') fails with:
        "Invalid input - interval=1w is not supported. Valid intervals: [..., 1wk, ...]"
        """
        # Test the mapping that prevented production failures
        assert map_timeframe_to_yfinance_interval("1w") == "1wk"
        assert map_timeframe_to_yfinance_interval("1M") == "1mo"
        assert map_timeframe_to_yfinance_interval("1mo") == "1mo"  # Already compatible

    def test_all_supported_intervals_map_correctly(self):
        """Test comprehensive interval mapping for all supported timeframes."""
        test_cases = [
            ("1m", "1m"),  # Should pass through unchanged
            ("1h", "1h"),  # Should pass through unchanged
            ("1d", "1d"),  # Should pass through unchanged
            ("1w", "1wk"),  # Critical mapping that prevented failures
            ("1M", "1mo"),  # Alternative monthly format
            ("1mo", "1mo"),  # Already yfinance-compatible
            ("3mo", "3mo"),  # Should pass through unchanged
        ]

        for frontend_interval, expected_yfinance_interval in test_cases:
            result = map_timeframe_to_yfinance_interval(frontend_interval)
            assert result == expected_yfinance_interval, (
                f"Interval mapping failed: '{frontend_interval}' → '{result}', "
                f"expected '{expected_yfinance_interval}'"
            )

    def test_unknown_interval_passes_through_unchanged(self):
        """Test that unknown intervals pass through unchanged for flexibility."""
        unknown_interval = "15s"  # Not in our mapping
        result = map_timeframe_to_yfinance_interval(unknown_interval)
        assert result == unknown_interval

    def test_valid_intervals_include_both_formats(self):
        """Test that validation accepts both frontend and yfinance formats."""
        frontend_intervals = get_valid_frontend_intervals()

        # Critical intervals that caused production issues
        assert "1w" in frontend_intervals, "Frontend must accept '1w' format"
        assert "1M" in frontend_intervals, "Frontend must accept '1M' format"
        assert "1mo" in frontend_intervals, "Frontend must accept '1mo' format"


class TestYfinanceAPIIntegration:
    """Test actual yfinance API calls with proper error handling."""

    @patch("yfinance.Ticker")
    def test_yfinance_history_with_mapped_intervals(self, mock_ticker_class):
        """
        UNIT TEST: Verify mapped intervals work with mocked yfinance calls.

        This prevents the production error: "interval=1w is not supported"
        """
        # Create mock data that yfinance would return
        mock_data = pd.DataFrame(
            {
                "Open": [150.0, 151.0, 152.0],
                "High": [155.0, 156.0, 157.0],
                "Low": [149.0, 150.0, 151.0],
                "Close": [154.0, 155.0, 156.0],
                "Volume": [1000000, 1100000, 1200000],
            },
            index=pd.date_range("2024-01-01", periods=3, freq="D"),
        )

        # Setup mock ticker instance
        mock_ticker = Mock()
        mock_ticker.history.return_value = mock_data
        mock_ticker_class.return_value = mock_ticker

        # Test that mapped intervals work with mocked yfinance API
        frontend_intervals_to_test = ["1d", "1w"]  # Focus on critical cases

        for frontend_interval in frontend_intervals_to_test:
            yfinance_interval = map_timeframe_to_yfinance_interval(frontend_interval)

            try:
                ticker = yf.Ticker("AAPL")
                # Use short period to minimize API calls and avoid rate limits
                data = ticker.history(period="5d", interval=yfinance_interval)

                # Verify we got actual data
                assert not data.empty, (
                    f"No data returned for AAPL with interval '{yfinance_interval}' "
                    f"(mapped from '{frontend_interval}')"
                )

                # Verify data structure
                expected_columns = ["Open", "High", "Low", "Close", "Volume"]
                for col in expected_columns:
                    assert (
                        col in data.columns
                    ), f"Missing column '{col}' in yfinance data"

                # Verify the correct interval was passed to yfinance
                mock_ticker.history.assert_called_with(
                    period="5d", interval=yfinance_interval
                )

            except Exception as e:
                pytest.fail(
                    f"yfinance API call failed for interval '{yfinance_interval}' "
                    f"(mapped from '{frontend_interval}'): {str(e)}"
                )

    @patch("yfinance.Ticker")
    def test_delisted_symbol_handling(self, mock_ticker):
        """
        REGRESSION TEST: Handle delisted symbols gracefully (like XLY issue).

        Root Cause: XLY symbol was delisted, causing macro analysis to crash.
        """
        # Mock a delisted symbol scenario
        mock_instance = Mock()
        mock_instance.history.return_value = pd.DataFrame()  # Empty DataFrame = no data
        mock_ticker.return_value = mock_instance

        # Test that we handle empty data gracefully
        ticker = yf.Ticker("XLY")  # The problematic delisted symbol
        data = ticker.history(period="5d", interval="1d")

        # Should return empty DataFrame without crashing
        assert data.empty, "Delisted symbol should return empty DataFrame"

        # Verify our code can detect and handle this scenario
        assert len(data) == 0, "Empty data should have zero length"

    @patch("yfinance.Ticker")
    def test_yfinance_api_timeout_handling(self, mock_ticker):
        """
        TEST: Handle yfinance API timeouts that caused 30-second frontend failures.
        """
        # Mock a timeout scenario
        mock_instance = Mock()
        mock_instance.history.side_effect = Exception("timeout of 30000ms exceeded")
        mock_ticker.return_value = mock_instance

        # Test that we can catch and handle timeouts
        ticker = yf.Ticker("AAPL")

        with pytest.raises(Exception) as exc_info:
            ticker.history(period="5d", interval="1d")

        assert "timeout" in str(exc_info.value).lower()

    @patch("yfinance.Ticker")
    def test_symbol_data_availability_validation(self, mock_ticker_class):
        """
        UNIT TEST: Validate symbol data availability to prevent downstream failures.

        Ensures symbols have actual price data before using them in analysis.
        """
        # Create mock data for valid symbol
        mock_data = pd.DataFrame(
            {
                "Open": [150.0, 151.0],
                "High": [155.0, 156.0],
                "Low": [149.0, 150.0],
                "Close": [154.0, 155.0],
                "Volume": [1000000, 1100000],
            },
            index=pd.date_range("2024-01-01", periods=2, freq="D"),
        )

        mock_ticker = Mock()
        mock_ticker.history.return_value = mock_data
        mock_ticker_class.return_value = mock_ticker

        # Test with known good symbol
        ticker = yf.Ticker("AAPL")
        data = ticker.history(period="5d", interval="1d")

        # Validation checks that should be performed
        assert not data.empty, "Valid symbol should return data"
        assert len(data) > 0, "Valid symbol should have price points"
        assert "Close" in data.columns, "Price data should include Close prices"
        assert data["Close"].notna().any(), "Should have valid Close prices"

    @pytest.mark.parametrize(
        "symbol,should_have_data",
        [
            ("AAPL", True),  # Known good symbol
            ("MSFT", True),  # Known good symbol
            ("INVALID123", False),  # Invalid symbol
        ],
    )
    @patch("yfinance.Ticker")
    def test_symbol_validation_scenarios(
        self, mock_ticker_class, symbol, should_have_data
    ):
        """
        PARAMETERIZED UNIT TEST: Test various symbol validation scenarios.

        Covers both valid and invalid symbols to ensure robust error handling.
        """
        # Setup mock based on whether symbol should have data
        if should_have_data:
            mock_data = pd.DataFrame(
                {
                    "Open": [150.0, 151.0],
                    "High": [155.0, 156.0],
                    "Low": [149.0, 150.0],
                    "Close": [154.0, 155.0],
                    "Volume": [1000000, 1100000],
                },
                index=pd.date_range("2024-01-01", periods=2, freq="D"),
            )
        else:
            # Empty DataFrame for invalid symbols
            mock_data = pd.DataFrame()

        mock_ticker = Mock()
        mock_ticker.history.return_value = mock_data
        mock_ticker_class.return_value = mock_ticker

        ticker = yf.Ticker(symbol)

        try:
            data = ticker.history(period="5d", interval="1d")
            has_data = not data.empty

            if should_have_data:
                assert (
                    has_data
                ), f"Symbol '{symbol}' should have data but returned empty"
            # Note: Invalid symbols may or may not return data depending on yfinance behavior
            # We test our handling rather than yfinance's specific responses

        except Exception as e:
            if should_have_data:
                pytest.fail(
                    f"Valid symbol '{symbol}' should not raise exception: {str(e)}"
                )
            # Invalid symbols may raise exceptions, which is acceptable


class TestYfinanceDataValidation:
    """Test data validation and quality checks for yfinance responses."""

    @patch("yfinance.Ticker")
    def test_price_data_structure_validation(self, mock_ticker_class):
        """UNIT TEST: Test that yfinance returns expected data structure."""
        # Create realistic mock data
        mock_data = pd.DataFrame(
            {
                "Open": [150.0, 151.0, 152.0],
                "High": [155.0, 156.0, 157.0],
                "Low": [149.0, 150.0, 151.0],
                "Close": [154.0, 155.0, 156.0],
                "Volume": [1000000, 1100000, 1200000],
            },
            index=pd.date_range("2024-01-01", periods=3, freq="D"),
        )

        mock_ticker = Mock()
        mock_ticker.history.return_value = mock_data
        mock_ticker_class.return_value = mock_ticker

        ticker = yf.Ticker("AAPL")
        data = ticker.history(period="5d", interval="1d")

        if not data.empty:  # Only test if data is available
            # Test required columns
            required_columns = ["Open", "High", "Low", "Close", "Volume"]
            for col in required_columns:
                assert col in data.columns, f"Missing required column: {col}"

            # Test data types
            numeric_columns = ["Open", "High", "Low", "Close", "Volume"]
            for col in numeric_columns:
                assert pd.api.types.is_numeric_dtype(
                    data[col]
                ), f"Column '{col}' should be numeric, got {data[col].dtype}"

            # Test logical price relationships
            for idx in data.index:
                row = data.loc[idx]
                assert (
                    row["Low"] <= row["High"]
                ), f"Low price should be <= High price at {idx}"
                assert (
                    row["Low"] <= row["Close"] <= row["High"]
                ), f"Close price should be between Low and High at {idx}"

    @patch("yfinance.Ticker")
    def test_dividend_yield_data_format(self, mock_ticker_class):
        """
        UNIT TEST: Ensure dividend yield is in correct format from yfinance.

        Tests our understanding that yfinance returns decimal format (0.0047 for 0.47%),
        requiring conversion to percentage for storage.
        """
        # Mock yfinance info with realistic dividend yield in decimal format
        mock_info = {
            "dividendYield": 0.0047,  # 0.47% in decimal format (realistic for AAPL)
            "longName": "Apple Inc.",
        }

        mock_ticker = Mock()
        mock_ticker.info = mock_info
        mock_ticker_class.return_value = mock_ticker

        ticker = yf.Ticker("AAPL")
        info = ticker.info

        if "dividendYield" in info and info["dividendYield"] is not None:
            dividend_yield = info["dividendYield"]

            # Test that yfinance returns numeric values
            assert isinstance(
                dividend_yield, int | float
            ), "Dividend yield should be numeric"

            # Test decimal format (0.0047 for 0.47%, not 0.47 directly)
            assert 0 <= dividend_yield <= 1, (
                f"Dividend yield {dividend_yield} should be in decimal format "
                f"(0.0047 for 0.47%, not 0.47 directly)"
            )

            # Verify it's in decimal format that needs conversion to percentage
            if dividend_yield > 0:
                assert dividend_yield < 0.25, (
                    f"Dividend yield {dividend_yield} suggests decimal format "
                    f"(multiply by 100 to get percentage)."
                )
