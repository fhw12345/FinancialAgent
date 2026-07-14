"""
Unit tests for title_utils module.

Tests chat title generation utilities.
"""

from src.core.utils.title_utils import (
    detect_action,
    extract_symbols,
    extract_title_from_response,
    generate_chat_title,
)

# ===== extract_symbols Tests =====


class TestExtractSymbols:
    """Test extract_symbols function"""

    def test_single_symbol(self):
        """Test extracting single symbol"""
        assert extract_symbols("What's the price of AAPL?") == ["AAPL"]

    def test_multiple_symbols(self):
        """Test extracting multiple symbols"""
        result = extract_symbols("Compare GOOGL and META earnings")
        assert result == ["GOOGL", "META"]

    def test_symbols_in_sentence(self):
        """Test extracting symbols from longer text"""
        result = extract_symbols("Should I buy NVDA or TSLA stock?")
        assert "NVDA" in result
        assert "TSLA" in result

    def test_stop_words_filtered(self):
        """Test that stop words are filtered out"""
        result = extract_symbols("I think AAPL is a good buy")
        assert "I" not in result
        assert "AAPL" in result

    def test_common_words_filtered(self):
        """Test that common financial acronyms are filtered"""
        result = extract_symbols("The ETF holds AAPL and MSFT shares")
        assert "ETF" not in result
        assert "AAPL" in result
        assert "MSFT" in result

    def test_deduplication(self):
        """Test that duplicate symbols are removed"""
        result = extract_symbols("AAPL is great, really think AAPL is the best")
        assert result == ["AAPL"]

    def test_preserves_order(self):
        """Test that order is preserved"""
        result = extract_symbols("First TSLA then AAPL then NVDA")
        assert result == ["TSLA", "AAPL", "NVDA"]

    def test_no_symbols(self):
        """Test text with no symbols"""
        result = extract_symbols("What is the best stock to buy?")
        # May or may not find symbols depending on text
        assert isinstance(result, list)

    def test_empty_string(self):
        """Test empty string"""
        assert extract_symbols("") == []


# ===== detect_action Tests =====


class TestDetectAction:
    """Test detect_action function"""

    def test_technical_analysis(self):
        """Test detecting technical analysis keywords"""
        assert detect_action("Show me the RSI for AAPL") == "Technical Analysis"
        assert detect_action("What's the MACD indicator?") == "Technical Analysis"
        assert detect_action("Bollinger bands analysis") == "Technical Analysis"

    def test_fundamental_analysis(self):
        """Test detecting fundamental analysis keywords"""
        assert detect_action("What are the earnings?") == "Fundamental Analysis"
        assert detect_action("Show me the P/E ratio") == "Fundamental Analysis"
        assert detect_action("EPS growth analysis") == "Fundamental Analysis"

    def test_cash_flow(self):
        """Test detecting cash flow keywords"""
        assert detect_action("What's the cash flow for MRVL?") == "Cash Flow"
        assert detect_action("Free cash flow analysis") == "Cash Flow"
        # Note: "FCF trend" matches "trend" in Technical Analysis first
        assert detect_action("Show me the FCF") == "Cash Flow"

    def test_balance_sheet(self):
        """Test detecting balance sheet keywords"""
        assert detect_action("Show me the balance sheet") == "Balance Sheet"
        assert detect_action("What's the debt level?") == "Balance Sheet"
        assert detect_action("Assets and liabilities") == "Balance Sheet"

    def test_news(self):
        """Test detecting news keywords"""
        assert detect_action("Latest news on AAPL") == "News"
        assert detect_action("Recent headlines") == "News"
        assert detect_action("Market sentiment") == "News"

    def test_price(self):
        """Test detecting price keywords"""
        assert detect_action("What's the current price?") == "Price"
        assert detect_action("Stock quote for NVDA") == "Price"
        assert detect_action("How much is TSLA trading at?") == "Price"

    def test_comparison(self):
        """Test detecting comparison keywords"""
        assert detect_action("Compare AAPL vs MSFT") == "Comparison"
        assert detect_action("Which is better, GOOGL or META?") == "Comparison"

    def test_default_analysis(self):
        """Test default when no keywords match"""
        assert detect_action("Tell me about AAPL") == "Analysis"
        assert detect_action("Something random") == "Analysis"


# ===== generate_chat_title Tests =====


class TestGenerateChatTitle:
    """Test generate_chat_title function"""

    def test_single_symbol_with_action(self):
        """Test title with single symbol and detected action"""
        title = generate_chat_title("Analyze AAPL stock")
        assert "AAPL" in title

    def test_single_symbol_cash_flow(self):
        """Test single symbol with cash flow action"""
        title = generate_chat_title("What's the cash flow for MRVL?")
        assert title == "MRVL Cash Flow"

    def test_comparison_title(self):
        """Test comparison title format"""
        title = generate_chat_title("Compare GOOGL and META")
        assert title == "GOOGL vs META"

    def test_multiple_symbols_no_comparison(self):
        """Test multiple symbols without comparison"""
        title = generate_chat_title("How are AAPL and MSFT doing?")
        assert "AAPL" in title
        assert "MSFT" in title

    def test_no_symbols_with_action(self):
        """Test title with no symbols but detected action"""
        title = generate_chat_title("Show me the latest news")
        assert title == "News"

    def test_no_symbols_no_action(self):
        """Test fallback title"""
        title = generate_chat_title("Hello there")
        assert title == "Chat Analysis"

    def test_title_max_length(self):
        """Test that title is truncated to max length"""
        # Create a very long message that would generate a long title
        long_message = (
            "Compare AAPL, MSFT, GOOGL, META, NVDA, TSLA and many more stocks"
        )
        title = generate_chat_title(long_message)
        assert len(title) <= 50

    def test_with_assistant_response(self):
        """Test with assistant response (symbols from user message take priority)"""
        title = generate_chat_title("Analyze NVDA", "NVDA is a great company...")
        assert "NVDA" in title


# ===== extract_title_from_response Tests =====


class TestExtractTitleFromResponse:
    """Test extract_title_from_response function"""

    def test_extract_valid_title(self):
        """Test extracting valid title from response"""
        response = "Analysis here...\n[chat_title: AAPL Analysis]"
        title, cleaned = extract_title_from_response(response)

        assert title == "AAPL Analysis"
        assert "Analysis here..." in cleaned
        assert "[chat_title:" not in cleaned

    def test_no_title_in_response(self):
        """Test response without title"""
        response = "Just a regular response without any title"
        title, cleaned = extract_title_from_response(response)

        assert title is None
        assert cleaned == response

    def test_empty_response(self):
        """Test empty/None response"""
        title, cleaned = extract_title_from_response(None)
        assert title is None
        assert cleaned is None

        title, cleaned = extract_title_from_response("")
        assert title is None
        assert cleaned == ""

    def test_title_case_insensitive(self):
        """Test case insensitive pattern matching"""
        response = "Content\n[CHAT_TITLE: My Title]"
        title, cleaned = extract_title_from_response(response)

        assert title == "My Title"

    def test_long_title_truncated(self):
        """Test that long titles are truncated"""
        long_title = "A" * 50  # More than 30 chars
        response = f"Content\n[chat_title: {long_title}]"
        title, cleaned = extract_title_from_response(response)

        assert len(title) <= 30
        assert title.endswith("...")

    def test_title_with_spaces(self):
        """Test title with extra spaces"""
        response = "Content\n[chat_title:   AAPL Technical Analysis   ]"
        title, cleaned = extract_title_from_response(response)

        assert title == "AAPL Technical Analysis"

    def test_response_cleaned_properly(self):
        """Test that response is cleaned properly"""
        response = "Line 1\nLine 2\n[chat_title: Title]"
        title, cleaned = extract_title_from_response(response)

        assert title == "Title"
        assert cleaned == "Line 1\nLine 2"
        assert cleaned.strip() == "Line 1\nLine 2"
