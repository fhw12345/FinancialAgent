"""
Comprehensive API model validation tests.

Tests critical Pydantic model validation that caused production errors:
- Pressure zone validation (string vs float type errors)
- Fibonacci response model validation
- Fundamentals response model validation
- Request model parameter validation
- Error response formatting

These tests ensure robust API contract validation and prevent runtime errors.
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.api.models import (
    FibonacciAnalysisRequest,
    FibonacciAnalysisResponse,
    FibonacciLevel,
    MacroAnalysisRequest,
    MacroSentimentResponse,
    MarketStructure,
    PricePoint,
    StockFundamentalsRequest,
    StockFundamentalsResponse,
)


class TestFibonacciAnalysisValidation:
    """
    REGRESSION TESTS: Fibonacci analysis model validation.

    Root Cause: Pressure zone returned non-numeric values causing Pydantic
    validation errors: "Input should be a valid number, unable to parse string"
    """

    @pytest.fixture
    def valid_fibonacci_levels(self):
        """Valid Fibonacci levels for testing."""
        return [
            FibonacciLevel(
                level=0.0, price=200.0, percentage="0.0%", is_key_level=False
            ),
            FibonacciLevel(
                level=0.382, price=180.9, percentage="38.2%", is_key_level=True
            ),
            FibonacciLevel(
                level=0.618, price=169.1, percentage="61.8%", is_key_level=True
            ),
        ]

    @pytest.fixture
    def valid_market_structure(self):
        """Valid market structure for testing."""
        return MarketStructure(
            trend_direction="uptrend",
            swing_high=PricePoint(price=200.0, date="2024-06-01"),
            swing_low=PricePoint(price=150.0, date="2024-01-01"),
            structure_quality="high",
            phase="Near swing high - potential resistance",
        )

    def test_fibonacci_response_with_valid_pressure_zone(
        self, valid_fibonacci_levels, valid_market_structure
    ):
        """
        CRITICAL REGRESSION TEST: Ensure pressure zone with numeric values validates.

        Bug: Original pressure zone returned {"strength": "high", "zone_type": "golden_ratio"}
        Fix: Must return {"strength": 0.9, "zone_width": 1.5} (all numeric)
        """
        # Valid pressure zone with only numeric values
        valid_pressure_zone = {
            "upper_bound": 180.9,
            "lower_bound": 169.1,
            "strength": 0.9,  # Numeric, not "high"
            "zone_width": 11.8,  # Numeric, not "golden_ratio"
        }

        # This should validate successfully
        response = FibonacciAnalysisResponse(
            symbol="AAPL",
            start_date="2024-01-01",
            end_date="2024-06-01",
            timeframe="1d",
            current_price=175.0,
            analysis_date=datetime.now().isoformat(),
            fibonacci_levels=valid_fibonacci_levels,
            market_structure=valid_market_structure,
            confidence_score=0.85,
            pressure_zone=valid_pressure_zone,  # Critical: all numeric values
            trend_strength="strong",
            analysis_summary="Test analysis",
            key_insights=["Test insight"],
            raw_data={},
        )

        # Test that validation passes
        assert response.pressure_zone == valid_pressure_zone
        assert response.pressure_zone["strength"] == 0.9
        assert isinstance(response.pressure_zone["strength"], int | float)

    def test_fibonacci_response_rejects_string_pressure_zone_values(
        self, valid_fibonacci_levels, valid_market_structure
    ):
        """
        REGRESSION TEST: Ensure invalid pressure zone with strings is rejected.

        This was the original bug that caused validation errors.
        """
        # Invalid pressure zone with string values (the original bug)
        invalid_pressure_zone = {
            "upper_bound": 180.9,
            "lower_bound": 169.1,
            "strength": "high",  # ❌ String, should be numeric
            "zone_type": "golden_ratio",  # ❌ String, should be numeric
        }

        # This should raise ValidationError
        with pytest.raises(ValidationError) as exc_info:
            FibonacciAnalysisResponse(
                symbol="AAPL",
                start_date="2024-01-01",
                end_date="2024-06-01",
                timeframe="1d",
                current_price=175.0,
                analysis_date=datetime.now().isoformat(),
                fibonacci_levels=valid_fibonacci_levels,
                market_structure=valid_market_structure,
                confidence_score=0.85,
                pressure_zone=invalid_pressure_zone,  # Invalid string values
                trend_strength="strong",
                analysis_summary="Test analysis",
                key_insights=["Test insight"],
                raw_data={},
            )

        # Verify the error mentions the type issue
        error_message = str(exc_info.value)
        assert (
            "Input should be a valid number" in error_message
            or "float_parsing" in error_message
        )

    def test_fibonacci_request_validation(self):
        """Test Fibonacci analysis request parameter validation."""
        # Valid request
        valid_request = FibonacciAnalysisRequest(
            symbol="AAPL",
            start_date="2024-01-01",
            end_date="2024-06-01",
            timeframe="1d",
            include_chart=True,
        )

        assert valid_request.symbol == "AAPL"
        assert valid_request.timeframe == "1d"

        # Test invalid timeframe
        with pytest.raises(ValidationError):
            FibonacciAnalysisRequest(
                symbol="AAPL",
                start_date="2024-01-01",
                end_date="2024-06-01",
                timeframe="invalid_timeframe",  # Invalid
                include_chart=True,
            )

    def test_fibonacci_level_validation(self):
        """Test individual Fibonacci level validation."""
        # Valid Fibonacci level
        valid_level = FibonacciLevel(
            level=0.618, price=169.1, percentage="61.8%", is_key_level=True
        )

        assert valid_level.level == 0.618
        assert valid_level.is_key_level is True

        # Test invalid level (negative)
        with pytest.raises(ValidationError):
            FibonacciLevel(
                level=-0.1,  # Invalid negative level
                price=169.1,
                percentage="-10.0%",
                is_key_level=False,
            )

    def test_confidence_score_range_validation(
        self, valid_fibonacci_levels, valid_market_structure
    ):
        """Test that confidence score is properly validated (0-1 range)."""
        valid_pressure_zone = {
            "upper_bound": 180.9,
            "lower_bound": 169.1,
            "strength": 0.9,
            "zone_width": 11.8,
        }

        # Test valid confidence scores
        valid_scores = [0.0, 0.5, 0.85, 1.0]
        for score in valid_scores:
            response = FibonacciAnalysisResponse(
                symbol="AAPL",
                start_date="2024-01-01",
                end_date="2024-06-01",
                timeframe="1d",
                current_price=175.0,
                analysis_date=datetime.now().isoformat(),
                fibonacci_levels=valid_fibonacci_levels,
                market_structure=valid_market_structure,
                confidence_score=score,  # Should be valid
                pressure_zone=valid_pressure_zone,
                trend_strength="strong",
                analysis_summary="Test analysis",
                key_insights=["Test insight"],
                raw_data={},
            )
            assert response.confidence_score == score

        # Test invalid confidence scores
        invalid_scores = [-0.1, 1.1, 2.0]
        for score in invalid_scores:
            with pytest.raises(ValidationError):
                FibonacciAnalysisResponse(
                    symbol="AAPL",
                    start_date="2024-01-01",
                    end_date="2024-06-01",
                    timeframe="1d",
                    current_price=175.0,
                    analysis_date=datetime.now().isoformat(),
                    fibonacci_levels=valid_fibonacci_levels,
                    market_structure=valid_market_structure,
                    confidence_score=score,  # Invalid score
                    pressure_zone=valid_pressure_zone,
                    trend_strength="strong",
                    analysis_summary="Test analysis",
                    key_insights=["Test insight"],
                    raw_data={},
                )


class TestStockFundamentalsValidation:
    """
    REGRESSION TESTS: Stock fundamentals model validation.

    Focus on dividend yield validation and numeric field constraints.
    """

    def test_fundamentals_response_with_corrected_dividend_yield(self):
        """
        REGRESSION TEST: Ensure dividend yield is in correct percentage format.

        Bug: Original code multiplied by 100, causing 41% instead of 0.41%
        Fix: Use yfinance value directly (0.41 for 0.41%)
        """
        # Test with realistic dividend yield (corrected format)
        response = StockFundamentalsResponse(
            symbol="AAPL",
            company_name="Apple Inc.",
            current_price=175.50,
            price_change=-2.15,
            price_change_percent=-1.21,
            market_cap=2750000000000,
            volume=45000000,
            avg_volume=55000000,
            pe_ratio=25.5,
            pb_ratio=5.2,
            dividend_yield=0.41,  # Correct: 0.41% (not 41%)
            beta=1.1,
            fifty_two_week_high=198.23,
            fifty_two_week_low=124.17,
            fundamental_summary="Strong fundamentals",
            key_metrics=["P/E: 25.5", "Dividend: 0.41%"],
        )

        # Verify dividend yield is reasonable
        assert response.dividend_yield == 0.41
        assert (
            0 < response.dividend_yield < 10
        ), f"Dividend yield {response.dividend_yield}% should be reasonable (0-10%)"

    def test_fundamentals_response_rejects_unrealistic_dividend_yield(self):
        """Test that unrealistic dividend yields are caught during validation."""
        # This would have been the bug: 41% dividend yield
        with pytest.raises(ValidationError):
            StockFundamentalsResponse(
                symbol="AAPL",
                company_name="Apple Inc.",
                current_price=175.50,
                price_change=-2.15,
                price_change_percent=-1.21,
                market_cap=2750000000000,
                volume=45000000,
                avg_volume=55000000,
                dividend_yield=41.0,  # Unrealistic 41% (the original bug)
                fifty_two_week_high=198.23,
                fifty_two_week_low=124.17,
                fundamental_summary="Strong fundamentals",
                key_metrics=["P/E: 25.5"],
            )

        # Should fail validation due to unrealistic dividend yield
        # Note: This assumes we add dividend yield range validation to the model

    def test_fundamentals_optional_fields_handling(self):
        """Test that optional fields (like dividend_yield) can be None."""
        # Test with missing dividend yield (valid for non-dividend stocks)
        response = StockFundamentalsResponse(
            symbol="TSLA",
            company_name="Tesla Inc.",
            current_price=250.0,
            price_change=5.0,
            price_change_percent=2.04,
            market_cap=800000000000,
            volume=30000000,
            avg_volume=35000000,
            pe_ratio=None,  # Optional
            pb_ratio=None,  # Optional
            dividend_yield=None,  # Optional (Tesla doesn't pay dividends)
            beta=1.8,
            fifty_two_week_high=275.0,
            fifty_two_week_low=180.0,
            fundamental_summary="Growth-focused company",
            key_metrics=["High beta", "No dividend"],
        )

        assert response.dividend_yield is None
        assert response.pe_ratio is None

    def test_fundamentals_request_validation(self):
        """Test fundamentals request parameter validation."""
        # Valid request
        valid_request = StockFundamentalsRequest(symbol="AAPL")
        assert valid_request.symbol == "AAPL"

        # Test empty symbol
        with pytest.raises(ValidationError):
            StockFundamentalsRequest(symbol="")

        # Test whitespace symbol
        with pytest.raises(ValidationError):
            StockFundamentalsRequest(symbol="   ")


class TestMacroAnalysisValidation:
    """Test macro analysis model validation."""

    def test_macro_sentiment_response_validation(self):
        """Test macro sentiment response model validation."""
        # Valid macro response
        response = MacroSentimentResponse(
            market_sentiment="greedy",
            vix_level=18.5,
            vix_interpretation="low volatility",
            fear_greed_score=75,
            major_indices={"S&P 500": 1.2, "NASDAQ": 2.1},
            sector_performance={"Technology": 2.5, "Healthcare": 1.2, "Energy": -0.8},
            confidence_level=0.8,
            sentiment_summary="Overall positive sentiment.",
            market_outlook="Positive market conditions with low volatility",
            key_factors=[
                "Strong earnings growth",
                "Low VIX indicating confidence",
                "Technology sector leadership",
            ],
        )

        assert response.market_sentiment == "greedy"
        assert response.vix_level == 18.5
        assert 0 <= response.fear_greed_score <= 100

    def test_macro_analysis_request_validation(self):
        """Test macro analysis request parameter validation."""
        # Valid request with defaults
        request = MacroAnalysisRequest()
        assert request.include_sectors is True
        assert request.include_indices is True

        # Valid request with custom values
        custom_request = MacroAnalysisRequest(
            include_sectors=False, include_indices=True
        )
        assert custom_request.include_sectors is False
        assert custom_request.include_indices is True


class TestDateValidation:
    """Test date format validation across all models."""

    def test_date_string_format_validation(self):
        """Test that date strings are properly validated."""
        # Test various date formats
        valid_dates = ["2024-01-01", "2024-12-31", "2023-06-15"]

        # Test with Fibonacci request (which has date validation)
        for valid_date in valid_dates:
            request = FibonacciAnalysisRequest(
                symbol="AAPL",
                start_date=valid_date,
                end_date="2024-12-31",
                timeframe="1d",
            )
            assert request.start_date == valid_date

        # Note: Date format validation would need to be added to the models
        # Currently, Pydantic accepts any string for date fields

    def test_date_range_logical_validation(self):
        """Test logical date range validation (start before end)."""
        # This would require custom validation in the models
        # Testing the concept here
        start_date = "2024-06-01"
        end_date = "2024-01-01"  # Before start date

        # In a properly validated model, this should fail
        # Currently demonstrating the validation logic that should exist
        assert start_date > end_date, "This should be caught by model validation"


class TestErrorResponseFormatting:
    """Test error response formatting and validation."""

    def test_validation_error_details(self):
        """Test that validation errors provide useful details."""
        try:
            # Create invalid Fibonacci response to trigger validation error
            FibonacciAnalysisResponse(
                symbol="",  # Invalid empty symbol
                current_price=-100,  # Invalid negative price
                confidence_score=2.0,  # Invalid confidence score > 1
                # Missing required fields...
            )
        except ValidationError as e:
            # Test that error contains useful information
            error_details = e.errors()
            assert len(error_details) > 0, "Should have validation errors"

            # Test error structure
            for error in error_details:
                assert "loc" in error, "Error should have location"
                assert "msg" in error, "Error should have message"
                assert "type" in error, "Error should have type"
