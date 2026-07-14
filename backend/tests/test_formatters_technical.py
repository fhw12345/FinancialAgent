"""
Unit tests for TechnicalFormatter.

Tests commodity price and technical indicator formatting.
"""

import pandas as pd
import pytest

from src.services.formatters.technical import TechnicalFormatter

# ===== Fixtures =====


@pytest.fixture
def commodity_df():
    """Sample commodity price DataFrame"""
    dates = pd.date_range(start="2024-01-01", periods=15, freq="MS")
    data = {
        "value": [
            4.0,
            4.1,
            4.2,
            4.15,
            4.3,
            4.4,
            4.35,
            4.5,
            4.6,
            4.55,
            4.7,
            4.8,
            4.75,
            4.9,
            5.0,
        ]
    }
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def single_indicator_df():
    """Sample single-value indicator DataFrame (RSI)"""
    dates = pd.date_range(start="2025-01-01", periods=12, freq="D")
    data = {"RSI": [45, 48, 52, 55, 60, 65, 68, 72, 70, 68, 65, 62]}
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def multi_indicator_df():
    """Sample multi-value indicator DataFrame (MACD)"""
    dates = pd.date_range(start="2025-01-01", periods=12, freq="D")
    data = {
        "MACD": [1.2, 1.5, 1.8, 2.0, 2.2, 2.0, 1.8, 1.5, 1.2, 1.0, 0.8, 1.0],
        "MACD_Signal": [1.0, 1.2, 1.4, 1.6, 1.8, 1.9, 1.8, 1.6, 1.4, 1.2, 1.0, 0.9],
        "MACD_Hist": [0.2, 0.3, 0.4, 0.4, 0.4, 0.1, 0.0, -0.1, -0.2, -0.2, -0.2, 0.1],
    }
    return pd.DataFrame(data, index=dates)


# ===== format_commodity_price Tests =====


class TestFormatCommodityPrice:
    """Test format_commodity_price method"""

    def test_format_basic(self, commodity_df):
        """Test basic commodity formatting"""
        result = TechnicalFormatter.format_commodity_price(
            df=commodity_df,
            commodity="COPPER",
            interval="monthly",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "# Copper Prices (Monthly)" in result
        assert "Current Price: $5.00" in result
        assert "Data Source: Alpha Vantage" in result

    def test_format_with_trend_analysis(self, commodity_df):
        """Test commodity formatting with trend analysis"""
        result = TechnicalFormatter.format_commodity_price(
            df=commodity_df,
            commodity="OIL",
            interval="monthly",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "Trend Analysis" in result
        assert "1-Period Change" in result
        assert "3-Period Change" in result
        assert "12-Period Change" in result

    def test_format_empty_df(self):
        """Test formatting empty DataFrame"""
        empty_df = pd.DataFrame(columns=["value"])
        result = TechnicalFormatter.format_commodity_price(
            df=empty_df,
            commodity="GOLD",
            interval="daily",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "No price data available" in result

    def test_format_price_history_table(self, commodity_df):
        """Test price history table is included"""
        result = TechnicalFormatter.format_commodity_price(
            df=commodity_df,
            commodity="SILVER",
            interval="weekly",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "Price History (Recent)" in result
        assert "| Date | Price | Change |" in result

    def test_format_strong_bullish_trend(self):
        """Test strong bullish trend detection"""
        dates = pd.date_range(start="2024-01-01", periods=15, freq="MS")
        # Price increases from 10 to 15 (+50%)
        data = {"value": [10 + i * 0.5 for i in range(15)]}
        df = pd.DataFrame(data, index=dates)

        result = TechnicalFormatter.format_commodity_price(
            df=df,
            commodity="COPPER",
            interval="monthly",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "Strong Bullish" in result

    def test_format_strong_bearish_trend(self):
        """Test strong bearish trend detection"""
        dates = pd.date_range(start="2024-01-01", periods=15, freq="MS")
        # Price decreases from 20 to 10 (-50%)
        data = {"value": [20 - i * 0.7 for i in range(15)]}
        df = pd.DataFrame(data, index=dates)

        result = TechnicalFormatter.format_commodity_price(
            df=df,
            commodity="OIL",
            interval="monthly",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "Strong Bearish" in result


# ===== format_technical_indicator Tests =====


class TestFormatTechnicalIndicator:
    """Test format_technical_indicator method"""

    def test_format_single_indicator(self, single_indicator_df):
        """Test formatting single-value indicator"""
        result = TechnicalFormatter.format_technical_indicator(
            df=single_indicator_df,
            symbol="AAPL",
            function="RSI",
            interval="daily",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "# RSI: AAPL" in result
        assert "Current RSI:" in result
        assert "Recent Values" in result

    def test_format_rsi_overbought(self):
        """Test RSI overbought signal"""
        dates = pd.date_range(start="2025-01-01", periods=5, freq="D")
        data = {"RSI": [65, 70, 75, 78, 75]}  # Overbought (>70)
        df = pd.DataFrame(data, index=dates)

        result = TechnicalFormatter.format_technical_indicator(
            df=df,
            symbol="AAPL",
            function="RSI",
            interval="daily",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "Overbought" in result

    def test_format_rsi_oversold(self):
        """Test RSI oversold signal"""
        dates = pd.date_range(start="2025-01-01", periods=5, freq="D")
        data = {"RSI": [35, 30, 25, 22, 25]}  # Oversold (<30)
        df = pd.DataFrame(data, index=dates)

        result = TechnicalFormatter.format_technical_indicator(
            df=df,
            symbol="AAPL",
            function="RSI",
            interval="daily",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "Oversold" in result

    def test_format_rsi_neutral(self):
        """Test RSI neutral signal"""
        dates = pd.date_range(start="2025-01-01", periods=5, freq="D")
        data = {"RSI": [45, 50, 55, 52, 50]}  # Neutral (30-70)
        df = pd.DataFrame(data, index=dates)

        result = TechnicalFormatter.format_technical_indicator(
            df=df,
            symbol="AAPL",
            function="RSI",
            interval="daily",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "Neutral" in result

    def test_format_multi_indicator(self, multi_indicator_df):
        """Test formatting multi-value indicator"""
        result = TechnicalFormatter.format_technical_indicator(
            df=multi_indicator_df,
            symbol="TSLA",
            function="MACD",
            interval="daily",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "# MACD: TSLA" in result
        assert "Current Values" in result
        assert "MACD" in result
        assert "MACD_Signal" in result

    def test_format_macd_bullish(self):
        """Test MACD bullish signal"""
        dates = pd.date_range(start="2025-01-01", periods=5, freq="D")
        data = {
            "MACD": [1.0, 1.2, 1.4, 1.6, 2.0],  # MACD above signal
            "MACD_Signal": [0.8, 1.0, 1.1, 1.2, 1.5],
        }
        df = pd.DataFrame(data, index=dates)

        result = TechnicalFormatter.format_technical_indicator(
            df=df,
            symbol="AAPL",
            function="MACD",
            interval="daily",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "Bullish" in result

    def test_format_macd_bearish(self):
        """Test MACD bearish signal"""
        dates = pd.date_range(start="2025-01-01", periods=5, freq="D")
        data = {
            "MACD": [1.0, 0.8, 0.6, 0.4, 0.2],  # MACD below signal
            "MACD_Signal": [1.2, 1.0, 0.9, 0.8, 0.5],
        }
        df = pd.DataFrame(data, index=dates)

        result = TechnicalFormatter.format_technical_indicator(
            df=df,
            symbol="AAPL",
            function="MACD",
            interval="daily",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "Bearish" in result

    def test_format_empty_indicator(self):
        """Test formatting empty indicator DataFrame"""
        empty_df = pd.DataFrame(columns=["RSI"])

        result = TechnicalFormatter.format_technical_indicator(
            df=empty_df,
            symbol="AAPL",
            function="RSI",
            interval="daily",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "No indicator data available" in result

    def test_format_recent_values_table(self, single_indicator_df):
        """Test recent values table formatting"""
        result = TechnicalFormatter.format_technical_indicator(
            df=single_indicator_df,
            symbol="MSFT",
            function="SMA",
            interval="weekly",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "Recent Values" in result
        assert "| Date |" in result
