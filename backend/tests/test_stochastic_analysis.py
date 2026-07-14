"""
Comprehensive unit tests for Stochastic Oscillator Analysis.
Tests core calculations, edge cases, data validation, and API integration.
"""

from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import pandas as pd
import pytest

from src.api.models import (
    StochasticAnalysisRequest,
    StochasticAnalysisResponse,
    StochasticLevel,
)
from src.core.analysis.stochastic_analyzer import StochasticAnalyzer
from src.core.data.ticker_data_service import TickerDataService


@pytest.fixture
def mock_ticker_data_service():
    """Create a mock TickerDataService for testing."""
    service = Mock(spec=TickerDataService)
    service.get_ticker_history = AsyncMock(return_value=pd.DataFrame())
    return service


class TestStochasticCalculations:
    """Test core stochastic oscillator calculations."""

    def test_stochastic_calculation_accuracy(self, mock_ticker_data_service):
        """Test that stochastic calculations are mathematically correct."""
        analyzer = StochasticAnalyzer(mock_ticker_data_service)

        # Create test data with sufficient points (30 data points for 14-period stochastic)
        np.random.seed(42)  # For reproducible results
        base_prices = np.linspace(100, 120, 30)
        noise = np.random.uniform(-2, 2, 30)

        test_data = pd.DataFrame(
            {
                "High": base_prices + noise + 2,
                "Low": base_prices + noise - 2,
                "Close": base_prices + noise,
            }
        )
        test_data.index = pd.date_range("2024-01-01", periods=len(test_data), freq="D")

        result = analyzer._calculate_stochastic(test_data, k_period=14, d_period=3)

        # Verify basic structure
        assert "slow_%k" in result.columns
        assert "slow_%d" in result.columns
        assert "fast_%k" in result.columns

        # Verify we have some valid calculations
        assert len(result.dropna()) > 0, "Should have valid stochastic calculations"

        # Verify K% is between 0 and 100 for valid values
        valid_k = result["slow_%k"].dropna()
        valid_d = result["slow_%d"].dropna()

        if len(valid_k) > 0:
            assert all(0 <= k <= 100 for k in valid_k)
        if len(valid_d) > 0:
            assert all(0 <= d <= 100 for d in valid_d)

        # Verify D% is smoother than K% (if we have enough data)
        if len(valid_k) > 3 and len(valid_d) > 3:
            k_std = valid_k.std()
            d_std = valid_d.std()
            if not np.isnan(k_std) and not np.isnan(d_std):
                assert (
                    d_std <= k_std + 1
                ), "D% should generally be smoother than K%"  # Allow small tolerance

    def test_stochastic_edge_case_all_same_prices(self, mock_ticker_data_service):
        """Test stochastic calculation when all prices are the same (edge case)."""
        analyzer = StochasticAnalyzer(mock_ticker_data_service)

        # All prices the same - should result in 50% stochastic (or handle division by zero)
        test_data = pd.DataFrame(
            {"High": [100] * 20, "Low": [100] * 20, "Close": [100] * 20}
        )
        test_data.index = pd.date_range("2024-01-01", periods=20, freq="D")

        result = analyzer._calculate_stochastic(test_data, k_period=14, d_period=3)

        # Should handle division by zero gracefully
        k_values = result["slow_%k"].dropna()
        if not k_values.empty:
            # If values exist, they should be valid numbers (not NaN or inf)
            assert all(np.isfinite(k) for k in k_values)

    def test_stochastic_insufficient_data(self, mock_ticker_data_service):
        """Test behavior with insufficient data points."""
        analyzer = StochasticAnalyzer(mock_ticker_data_service)

        # Only 5 data points, requesting 14-period stochastic
        test_data = pd.DataFrame(
            {
                "High": [110, 115, 120, 118, 125],
                "Low": [105, 108, 112, 110, 115],
                "Close": [108, 112, 118, 115, 120],
            }
        )
        test_data.index = pd.date_range("2024-01-01", periods=5, freq="D")

        result = analyzer._calculate_stochastic(test_data, k_period=14, d_period=3)

        # Should return empty or minimal data without crashing
        assert isinstance(result, pd.DataFrame)
        # With insufficient data, should have no or very few valid calculations
        valid_rows = result.dropna()
        assert (
            len(valid_rows) == 0
        ), "Should have no valid calculations with insufficient data"


class TestStochasticSignalDetection:
    """Test signal detection logic."""

    def test_signal_determination_boundaries(self, mock_ticker_data_service):
        """Test overbought/oversold signal boundaries."""
        analyzer = StochasticAnalyzer(mock_ticker_data_service)

        # Test boundary conditions
        assert analyzer._determine_signal(85.0) == "overbought"
        assert analyzer._determine_signal(80.0) == "overbought"  # Exactly at boundary
        assert analyzer._determine_signal(79.9) == "neutral"

        assert analyzer._determine_signal(15.0) == "oversold"
        assert analyzer._determine_signal(20.0) == "oversold"  # Exactly at boundary
        assert analyzer._determine_signal(20.1) == "neutral"

        assert analyzer._determine_signal(50.0) == "neutral"
        assert analyzer._determine_signal(65.0) == "neutral"

    def test_crossover_detection_accuracy(self, mock_ticker_data_service):
        """Test that crossover signals are detected correctly."""
        analyzer = StochasticAnalyzer(mock_ticker_data_service)

        # Create data with clear crossover pattern
        test_data = pd.DataFrame(
            {
                "High": [100] * 20,
                "Low": [80] * 20,
                "Close": [90] * 20,
                "slow_%k": [
                    30,
                    35,
                    45,
                    55,
                    65,
                    70,
                    68,
                    62,
                    55,
                    48,
                    42,
                    38,
                    35,
                    40,
                    45,
                    50,
                    55,
                    60,
                    65,
                    70,
                ],
                "slow_%d": [
                    32,
                    36,
                    42,
                    48,
                    58,
                    68,
                    69,
                    67,
                    62,
                    55,
                    48,
                    42,
                    38,
                    38,
                    40,
                    45,
                    50,
                    55,
                    60,
                    65,
                ],
            }
        )
        test_data.index = pd.date_range("2024-01-01", periods=20, freq="D")

        signals = analyzer._analyze_crossovers(test_data, lookback_days=20)

        # Should detect crossovers
        assert len(signals) > 0

        # Verify signal structure
        for signal in signals:
            assert "type" in signal
            assert "date" in signal
            assert "description" in signal
            assert signal["type"] in ["buy", "sell"]

    def test_divergence_detection_basic(self, mock_ticker_data_service):
        """Test basic divergence detection functionality."""
        analyzer = StochasticAnalyzer(mock_ticker_data_service)

        # Create data with potential divergence pattern
        test_data = pd.DataFrame(
            {
                "Close": np.concatenate(
                    [
                        np.linspace(100, 110, 30),  # Rising price
                        np.linspace(110, 120, 30),  # Higher high
                        np.linspace(120, 115, 30),  # Slight pullback
                    ]
                ),
                "slow_%k": np.concatenate(
                    [
                        np.linspace(30, 70, 30),  # Rising oscillator
                        np.linspace(70, 65, 30),  # Lower high (divergence)
                        np.linspace(65, 60, 30),  # Continued weakness
                    ]
                ),
            }
        )
        test_data.index = pd.date_range("2024-01-01", periods=90, freq="D")

        divergences = analyzer._analyze_divergence(test_data, lookback_period=90)

        # Should not crash and return list
        assert isinstance(divergences, list)

        # If divergences found, verify structure
        for div in divergences:
            assert "type" in div
            assert "description" in div
            assert div["type"] in ["bullish", "bearish"]


class TestStochasticAnalysisModels:
    """Test API model validation and data contracts."""

    def test_stochastic_request_validation(self):
        """Test request model validation."""
        # Valid request
        valid_request = StochasticAnalysisRequest(
            symbol="AAPL",
            start_date="2024-01-01",
            end_date="2024-12-31",
            timeframe="1d",
            k_period=14,
            d_period=3,
        )
        assert valid_request.symbol == "AAPL"
        assert valid_request.k_period == 14
        assert valid_request.d_period == 3

        # Test defaults
        default_request = StochasticAnalysisRequest(symbol="TSLA")
        assert default_request.timeframe == "1d"
        assert default_request.k_period == 14
        assert default_request.d_period == 3

        # Invalid K period (too low)
        with pytest.raises(ValueError):
            StochasticAnalysisRequest(symbol="AAPL", k_period=2)

        # Invalid K period (too high)
        with pytest.raises(ValueError):
            StochasticAnalysisRequest(symbol="AAPL", k_period=60)

        # Invalid D period
        with pytest.raises(ValueError):
            StochasticAnalysisRequest(symbol="AAPL", d_period=1)

    def test_stochastic_level_validation(self):
        """Test StochasticLevel model validation."""
        # Valid level
        valid_level = StochasticLevel(
            timestamp="2024-01-01 12:00:00",
            k_percent=75.5,
            d_percent=72.3,
            signal="overbought",
        )
        assert valid_level.k_percent == 75.5
        assert valid_level.signal == "overbought"

        # Test boundary values
        boundary_level = StochasticLevel(
            timestamp="2024-01-01 12:00:00",
            k_percent=0.0,
            d_percent=100.0,
            signal="oversold",
        )
        assert boundary_level.k_percent == 0.0
        assert boundary_level.d_percent == 100.0

        # Invalid K percent (negative)
        with pytest.raises(ValueError):
            StochasticLevel(
                timestamp="2024-01-01 12:00:00",
                k_percent=-5.0,
                d_percent=50.0,
                signal="neutral",
            )

        # Invalid signal
        with pytest.raises(ValueError):
            StochasticLevel(
                timestamp="2024-01-01 12:00:00",
                k_percent=50.0,
                d_percent=50.0,
                signal="invalid_signal",
            )

    def test_stochastic_response_model_completeness(self):
        """Test that response model includes all required fields."""
        # Sample response data
        sample_response = StochasticAnalysisResponse(
            symbol="AAPL",
            start_date="2024-01-01",
            end_date="2024-12-31",
            timeframe="1d",
            current_price=150.25,
            k_period=14,
            d_period=3,
            current_k=75.5,
            current_d=72.3,
            current_signal="overbought",
            stochastic_levels=[],
            signal_changes=[],
            analysis_summary="Test analysis",
            key_insights=["Test insight"],
            raw_data={"test": "data"},
        )

        # Verify all required fields are present
        assert sample_response.symbol == "AAPL"
        assert sample_response.timeframe == "1d"
        assert sample_response.current_signal == "overbought"
        assert 0 <= sample_response.current_k <= 100
        assert 0 <= sample_response.current_d <= 100
        assert isinstance(sample_response.stochastic_levels, list)
        assert isinstance(sample_response.signal_changes, list)
        assert isinstance(sample_response.key_insights, list)


class TestStochasticAnalysisIntegration:
    """Test full analysis workflow and error handling."""

    @pytest.mark.asyncio
    async def test_analyzer_with_valid_symbol(self, mock_ticker_data_service):
        """Test analyzer with valid symbol and mock data."""
        analyzer = StochasticAnalyzer(mock_ticker_data_service)

        # Mock yfinance data
        mock_data = pd.DataFrame(
            {
                "High": np.random.uniform(100, 110, 50),
                "Low": np.random.uniform(90, 100, 50),
                "Close": np.random.uniform(95, 105, 50),
            }
        )
        mock_data.index = pd.date_range("2024-01-01", periods=50, freq="D")

        with patch.object(analyzer, "_fetch_stock_data") as mock_fetch:
            mock_fetch.return_value = mock_data

            result = await analyzer.analyze(
                symbol="AAPL",
                start_date="2024-01-01",
                end_date="2024-02-19",
                timeframe="1d",
                k_period=14,
                d_period=3,
            )

            # Verify response structure
            assert isinstance(result, StochasticAnalysisResponse)
            assert result.symbol == "AAPL"
            assert result.timeframe == "1d"
            assert result.k_period == 14
            assert result.d_period == 3
            assert result.current_signal in ["overbought", "oversold", "neutral"]
            assert len(result.key_insights) > 0
            assert len(result.analysis_summary) > 0

    @pytest.mark.asyncio
    async def test_analyzer_with_insufficient_data(self, mock_ticker_data_service):
        """Test analyzer behavior with insufficient data."""
        analyzer = StochasticAnalyzer(mock_ticker_data_service)

        # Mock minimal data (insufficient for 14-period stochastic)
        mock_data = pd.DataFrame(
            {"High": [105, 110, 108], "Low": [100, 105, 103], "Close": [102, 107, 105]}
        )
        mock_data.index = pd.date_range("2024-01-01", periods=3, freq="D")

        with patch.object(analyzer, "_fetch_stock_data") as mock_fetch:
            mock_fetch.return_value = mock_data

            with pytest.raises(ValueError, match="Insufficient data"):
                await analyzer.analyze(
                    symbol="TEST", timeframe="1d", k_period=14, d_period=3
                )

    @pytest.mark.asyncio
    async def test_analyzer_with_invalid_symbol(self, mock_ticker_data_service):
        """Test analyzer with invalid/delisted symbol."""
        analyzer = StochasticAnalyzer(mock_ticker_data_service)

        with patch.object(analyzer, "_fetch_stock_data") as mock_fetch:
            mock_fetch.return_value = pd.DataFrame()  # Empty data

            with pytest.raises(ValueError, match="not a valid stock symbol"):
                await analyzer.analyze(symbol="INVALID123", timeframe="1d")

    @pytest.mark.asyncio
    async def test_analyzer_different_timeframes(self, mock_ticker_data_service):
        """Test analyzer with different timeframes."""
        analyzer = StochasticAnalyzer(mock_ticker_data_service)

        # Mock data for different timeframes
        mock_data = pd.DataFrame(
            {
                "High": np.random.uniform(100, 110, 100),
                "Low": np.random.uniform(90, 100, 100),
                "Close": np.random.uniform(95, 105, 100),
            }
        )
        mock_data.index = pd.date_range("2024-01-01", periods=100, freq="h")

        timeframes = ["1h", "1d", "1w", "1M"]

        for timeframe in timeframes:
            with patch.object(analyzer, "_fetch_stock_data") as mock_fetch:
                mock_fetch.return_value = mock_data

                result = await analyzer.analyze(
                    symbol="AAPL", timeframe=timeframe, k_period=14, d_period=3
                )

                assert result.timeframe == timeframe
                assert isinstance(result, StochasticAnalysisResponse)


class TestStochasticErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_network_error_handling(self, mock_ticker_data_service):
        """Test handling of network errors during data fetch."""
        analyzer = StochasticAnalyzer(mock_ticker_data_service)

        with patch.object(analyzer, "_fetch_stock_data") as mock_fetch:
            mock_fetch.side_effect = Exception("Network error")

            with pytest.raises(Exception, match="Network error"):
                await analyzer.analyze(symbol="AAPL", timeframe="1d")

    def test_empty_dataframe_handling(self, mock_ticker_data_service):
        """Test handling of empty DataFrames."""
        analyzer = StochasticAnalyzer(mock_ticker_data_service)

        empty_df = pd.DataFrame()
        result = analyzer._calculate_stochastic(empty_df)

        # Should handle gracefully
        assert isinstance(result, pd.DataFrame)

    def test_malformed_data_handling(self, mock_ticker_data_service):
        """Test handling of malformed price data."""
        analyzer = StochasticAnalyzer(mock_ticker_data_service)

        # Missing required columns
        bad_data = pd.DataFrame(
            {
                "High": [100, 110, 105],
                # Missing 'Low' and 'Close'
            }
        )

        # Should return empty DataFrame for malformed data
        result = analyzer._calculate_stochastic(bad_data)
        assert result.empty

    def test_extreme_parameter_values(self, mock_ticker_data_service):
        """Test analyzer with extreme parameter values."""
        analyzer = StochasticAnalyzer(mock_ticker_data_service)

        test_data = pd.DataFrame(
            {"High": [110] * 100, "Low": [90] * 100, "Close": [100] * 100}
        )
        test_data.index = pd.date_range("2024-01-01", periods=100, freq="D")

        # Test with minimum valid parameters
        result = analyzer._calculate_stochastic(test_data, k_period=5, d_period=2)
        assert isinstance(result, pd.DataFrame)

        # Test with maximum valid parameters
        result = analyzer._calculate_stochastic(test_data, k_period=50, d_period=20)
        assert isinstance(result, pd.DataFrame)


class TestDataContractValidation:
    """Test data contracts between components."""

    def test_frontend_backend_type_alignment(self):
        """Test that frontend TypeScript types align with backend Pydantic models."""
        # Test request model matches expected frontend interface
        request = StochasticAnalysisRequest(
            symbol="AAPL",
            start_date="2024-01-01",
            end_date="2024-12-31",
            timeframe="1d",
            k_period=14,
            d_period=3,
        )

        # Should serialize to match frontend expectations
        request_dict = request.model_dump()
        expected_keys = {
            "symbol",
            "start_date",
            "end_date",
            "timeframe",
            "k_period",
            "d_period",
        }
        assert set(request_dict.keys()) == expected_keys

        # Timeframe should be one of supported values
        assert request.timeframe in ["1h", "1d", "1w", "1M"]

    def test_response_serialization_format(self):
        """Test that response serializes correctly for frontend consumption."""
        sample_level = StochasticLevel(
            timestamp="2024-01-01T12:00:00",
            k_percent=75.5,
            d_percent=72.3,
            signal="overbought",
        )

        response = StochasticAnalysisResponse(
            symbol="AAPL",
            timeframe="1d",
            current_price=150.25,
            k_period=14,
            d_period=3,
            current_k=75.5,
            current_d=72.3,
            current_signal="overbought",
            stochastic_levels=[sample_level],
            signal_changes=[{"type": "buy", "date": "2024-01-01"}],
            analysis_summary="Test analysis",
            key_insights=["Test insight"],
            raw_data={"test": "data"},
        )

        # Should serialize without errors
        response_dict = response.model_dump()
        assert "symbol" in response_dict
        assert "current_signal" in response_dict
        assert "stochastic_levels" in response_dict

        # Signal values should be valid
        assert response_dict["current_signal"] in ["overbought", "oversold", "neutral"]

        # Levels should serialize correctly
        assert len(response_dict["stochastic_levels"]) == 1
        level_dict = response_dict["stochastic_levels"][0]
        assert level_dict["signal"] == "overbought"
        assert 0 <= level_dict["k_percent"] <= 100
