"""
Unit tests for formatters module.

Tests number formatting, type conversion, and display helpers.
"""

from src.shared.formatters import (
    calculate_qoq_growth,
    format_large_number,
    format_metric_value,
    format_percentage,
    safe_float,
    safe_int,
)

# ===== safe_float Tests =====


class TestSafeFloat:
    """Test safe_float function"""

    def test_string_conversion(self):
        """Test converting string to float"""
        assert safe_float("123.45") == 123.45
        assert safe_float("0.5") == 0.5
        assert safe_float("-10.5") == -10.5

    def test_number_passthrough(self):
        """Test that numbers pass through"""
        assert safe_float(42.0) == 42.0
        assert safe_float(100) == 100.0

    def test_none_handling(self):
        """Test None value handling"""
        assert safe_float(None) == 0.0
        assert safe_float(None, -1.0) == -1.0

    def test_string_none_handling(self):
        """Test 'None' string handling"""
        assert safe_float("None") == 0.0
        assert safe_float("None", 99.0) == 99.0

    def test_empty_string(self):
        """Test empty string handling"""
        assert safe_float("") == 0.0
        assert safe_float("", 5.0) == 5.0

    def test_invalid_string(self):
        """Test invalid string handling"""
        assert safe_float("invalid") == 0.0
        assert safe_float("abc123", -1.0) == -1.0
        assert safe_float("N/A") == 0.0

    def test_custom_default(self):
        """Test custom default value"""
        assert safe_float(None, 99.99) == 99.99
        assert safe_float("bad", 42.0) == 42.0


# ===== safe_int Tests =====


class TestSafeInt:
    """Test safe_int function"""

    def test_string_conversion(self):
        """Test converting string to int"""
        assert safe_int("123") == 123
        assert safe_int("-50") == -50

    def test_float_string_conversion(self):
        """Test converting float string to int (truncates)"""
        assert safe_int("123.45") == 123
        assert safe_int("99.9") == 99

    def test_float_conversion(self):
        """Test converting float to int"""
        assert safe_int(45.7) == 45
        assert safe_int(99.99) == 99

    def test_none_handling(self):
        """Test None value handling"""
        assert safe_int(None) == 0
        assert safe_int(None, -1) == -1

    def test_string_none_handling(self):
        """Test 'None' string handling"""
        assert safe_int("None") == 0

    def test_empty_string(self):
        """Test empty string handling"""
        assert safe_int("") == 0

    def test_invalid_string(self):
        """Test invalid string handling"""
        assert safe_int("invalid") == 0
        assert safe_int("abc", 99) == 99


# ===== format_large_number Tests =====


class TestFormatLargeNumber:
    """Test format_large_number function"""

    def test_billions(self):
        """Test formatting billions"""
        assert format_large_number(1_500_000_000) == "$1.50B"
        assert format_large_number(10_000_000_000) == "$10.00B"

    def test_millions(self):
        """Test formatting millions"""
        assert format_large_number(250_300_000) == "$250.3M"
        assert format_large_number(1_500_000) == "$1.5M"

    def test_thousands(self):
        """Test formatting thousands"""
        assert format_large_number(150_000) == "$150.0K"
        assert format_large_number(1_500) == "$1.5K"

    def test_small_numbers(self):
        """Test formatting small numbers"""
        assert format_large_number(999) == "$999.00"
        assert format_large_number(50) == "$50.00"

    def test_none_value(self):
        """Test None value handling"""
        assert format_large_number(None) == "N/A"

    def test_zero_value(self):
        """Test zero value handling"""
        # Note: Implementation only checks float 0.0, not int 0
        # Integer 0 formats as "$0.00"
        assert format_large_number(0) == "$0.00"
        assert format_large_number(0.0) == "N/A"

    def test_no_currency_prefix(self):
        """Test without currency prefix"""
        assert format_large_number(1500, currency_prefix="") == "1.5K"
        assert format_large_number(1_500_000, currency_prefix="") == "1.5M"

    def test_with_sign(self):
        """Test including +/- sign"""
        assert format_large_number(1_000_000, include_sign=True) == "+$1.0M"
        # Note: negative numbers would show minus naturally


# ===== format_percentage Tests =====


class TestFormatPercentage:
    """Test format_percentage function"""

    def test_positive_percentage(self):
        """Test formatting positive percentages"""
        assert format_percentage(5.234) == "+5.2%"
        assert format_percentage(100.0) == "+100.0%"

    def test_negative_percentage(self):
        """Test formatting negative percentages"""
        assert format_percentage(-2.1) == "-2.1%"
        assert format_percentage(-50.5) == "-50.5%"

    def test_zero_percentage(self):
        """Test formatting zero"""
        assert format_percentage(0) == "+0.0%"

    def test_custom_decimal_places(self):
        """Test custom decimal places"""
        assert format_percentage(-2.123, decimal_places=2) == "-2.12%"
        assert format_percentage(5.6789, decimal_places=3) == "+5.679%"

    def test_without_sign(self):
        """Test without +/- sign"""
        assert format_percentage(5.2, include_sign=False) == "5.2%"
        assert format_percentage(-2.1, include_sign=False) == "-2.1%"

    def test_none_value(self):
        """Test None value handling"""
        assert format_percentage(None) == "N/A"


# ===== calculate_qoq_growth Tests =====


class TestCalculateQoqGrowth:
    """Test calculate_qoq_growth function"""

    def test_positive_growth(self):
        """Test positive quarter-over-quarter growth"""
        result = calculate_qoq_growth(105, 100)
        assert result == "+5.0%"

    def test_negative_growth(self):
        """Test negative quarter-over-quarter growth"""
        result = calculate_qoq_growth(98, 100)
        assert result == "-2.0%"

    def test_zero_growth(self):
        """Test no growth"""
        result = calculate_qoq_growth(100, 100)
        assert result == "+0.0%"

    def test_large_growth(self):
        """Test large growth percentage"""
        result = calculate_qoq_growth(200, 100)
        assert result == "+100.0%"

    def test_none_current(self):
        """Test None current value"""
        assert calculate_qoq_growth(None, 100) == "N/A"

    def test_none_previous(self):
        """Test None previous value"""
        assert calculate_qoq_growth(100, None) == "N/A"

    def test_zero_previous(self):
        """Test zero previous value (division by zero)"""
        assert calculate_qoq_growth(100, 0) == "N/A"


# ===== format_metric_value Tests =====


class TestFormatMetricValue:
    """Test format_metric_value function"""

    def test_currency_type(self):
        """Test currency formatting"""
        assert format_metric_value(1_500_000, "currency") == "$1.5M"
        assert format_metric_value(1_000_000_000, "currency") == "$1.00B"

    def test_percentage_type(self):
        """Test percentage formatting (input is decimal)"""
        assert format_metric_value(0.125, "percentage") == "+12.5%"
        assert format_metric_value(-0.05, "percentage") == "-5.0%"

    def test_ratio_type(self):
        """Test ratio formatting"""
        assert format_metric_value(15.234, "ratio") == "15.23"
        assert format_metric_value(1.5, "ratio") == "1.50"

    def test_number_type_large(self):
        """Test number formatting for large values"""
        assert format_metric_value(10_000, "number") == "10.0K"

    def test_number_type_small(self):
        """Test number formatting for small values"""
        assert format_metric_value(50.123, "number") == "50.12"

    def test_none_value(self):
        """Test None value handling"""
        assert format_metric_value(None, "currency") == "N/A"
        assert format_metric_value("None", "percentage") == "N/A"

    def test_custom_decimal_places(self):
        """Test custom decimal places for ratio"""
        assert format_metric_value(3.14159, "ratio", decimal_places=3) == "3.142"

    def test_string_conversion(self):
        """Test string value conversion"""
        assert format_metric_value("100.5", "ratio") == "100.50"
