"""
Unit tests for financial analysis module exports.

Tests that the core financial analysis module properly exports all analyzer components.
"""

from src.core import financial_analysis


class TestFinancialAnalysisExports:
    """Test that financial_analysis module exports expected components"""

    def test_module_has_all_exports(self):
        """Test that __all__ contains all expected exports"""
        # Assert
        expected_exports = [
            "FibonacciAnalyzer",
            "MacroAnalyzer",
            "StockAnalyzer",
            "StochasticAnalyzer",
            "StockDataFetcher",
        ]
        assert set(financial_analysis.__all__) == set(expected_exports)

    def test_fibonacci_analyzer_importable(self):
        """Test that FibonacciAnalyzer can be imported"""
        # Act & Assert
        assert hasattr(financial_analysis, "FibonacciAnalyzer")
        assert financial_analysis.FibonacciAnalyzer is not None

    def test_macro_analyzer_importable(self):
        """Test that MacroAnalyzer can be imported"""
        # Act & Assert
        assert hasattr(financial_analysis, "MacroAnalyzer")
        assert financial_analysis.MacroAnalyzer is not None

    def test_stock_analyzer_importable(self):
        """Test that StockAnalyzer can be imported"""
        # Act & Assert
        assert hasattr(financial_analysis, "StockAnalyzer")
        assert financial_analysis.StockAnalyzer is not None

    def test_stochastic_analyzer_importable(self):
        """Test that StochasticAnalyzer can be imported"""
        # Act & Assert
        assert hasattr(financial_analysis, "StochasticAnalyzer")
        assert financial_analysis.StochasticAnalyzer is not None

    def test_stock_data_fetcher_importable(self):
        """Test that StockDataFetcher can be imported"""
        # Act & Assert
        assert hasattr(financial_analysis, "StockDataFetcher")
        assert financial_analysis.StockDataFetcher is not None

    def test_all_exports_are_accessible(self):
        """Test that all __all__ exports are accessible as attributes"""
        # Act & Assert
        for export_name in financial_analysis.__all__:
            assert hasattr(
                financial_analysis, export_name
            ), f"{export_name} not accessible"

    def test_can_import_all_from_module(self):
        """Test that 'from financial_analysis import *' works"""
        # Arrange
        namespace = {}

        # Act
        exec("from src.core.financial_analysis import *", namespace)

        # Assert - all __all__ items should be in namespace
        for export_name in financial_analysis.__all__:
            assert export_name in namespace, f"{export_name} not in namespace"
