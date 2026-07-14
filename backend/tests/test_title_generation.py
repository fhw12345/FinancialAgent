"""
Unit tests for chat title generation utilities.

Tests symbol extraction, action detection, and title generation.
"""

from src.core.utils.title_utils import (
    MAX_TITLE_LENGTH,
    detect_action,
    extract_symbols,
    extract_title_from_response,
    generate_chat_title,
)


class TestExtractSymbols:
    """Test symbol extraction from text."""

    def test_single_symbol(self):
        """Extract single symbol from text."""
        symbols = extract_symbols("What's the price of AAPL?")
        assert symbols == ["AAPL"]

    def test_multiple_symbols(self):
        """Extract multiple symbols from text."""
        symbols = extract_symbols("Compare GOOGL and META earnings")
        assert symbols == ["GOOGL", "META"]

    def test_duplicates_removed(self):
        """Duplicate symbols are deduplicated."""
        symbols = extract_symbols("Buy AAPL, hold AAPL, sell AAPL")
        assert symbols == ["AAPL"]

    def test_stop_words_filtered(self):
        """Common words that look like symbols are filtered."""
        symbols = extract_symbols("I want to analyze THE stock")
        assert "I" not in symbols
        assert "THE" not in symbols

    def test_empty_text(self):
        """Empty text returns empty list."""
        symbols = extract_symbols("")
        assert symbols == []

    def test_no_symbols(self):
        """Text without symbols returns empty list."""
        symbols = extract_symbols("How's my portfolio doing?")
        assert symbols == []

    def test_lowercase_not_matched(self):
        """Lowercase text is not matched as symbols."""
        symbols = extract_symbols("aapl msft nvda")
        assert symbols == []

    def test_preserves_order(self):
        """Symbols returned in order of first occurrence."""
        symbols = extract_symbols("First NVDA then AAPL then NVDA again")
        assert symbols == ["NVDA", "AAPL"]

    def test_etf_symbols(self):
        """ETF symbols are extracted correctly."""
        symbols = extract_symbols("What's in the QQQ and SPY ETFs?")
        assert "QQQ" in symbols
        assert "SPY" in symbols


class TestDetectAction:
    """Test action detection from text."""

    def test_technical_analysis(self):
        """Detect technical analysis keywords."""
        assert detect_action("Show me the RSI for AAPL") == "Technical Analysis"
        assert detect_action("Calculate MACD") == "Technical Analysis"
        assert detect_action("Draw the support levels") == "Technical Analysis"

    def test_fundamental_analysis(self):
        """Detect fundamental analysis keywords."""
        assert detect_action("What are the earnings?") == "Fundamental Analysis"
        assert detect_action("Check the P/E ratio") == "Fundamental Analysis"
        assert detect_action("Revenue growth analysis") == "Fundamental Analysis"

    def test_cash_flow(self):
        """Detect cash flow keywords."""
        assert detect_action("What's the cash flow for MRVL?") == "Cash Flow"
        assert detect_action("Show FCF data") == "Cash Flow"
        assert detect_action("Operating cashflow analysis") == "Cash Flow"
        assert detect_action("Free cash flow report") == "Cash Flow"

    def test_balance_sheet(self):
        """Detect balance sheet keywords."""
        assert detect_action("Review the balance sheet") == "Balance Sheet"
        assert detect_action("Total assets and liabilities") == "Balance Sheet"
        assert detect_action("What's the debt ratio?") == "Balance Sheet"

    def test_news(self):
        """Detect news keywords."""
        assert detect_action("Latest news on TSLA") == "News"
        assert detect_action("Market sentiment analysis") == "News"

    def test_price_quote(self):
        """Detect price quote keywords."""
        assert detect_action("What's the current price?") == "Price"
        assert detect_action("Get quote for NVDA") == "Price"

    def test_comparison(self):
        """Detect comparison keywords."""
        assert detect_action("Compare GOOGL and META") == "Comparison"
        assert detect_action("Which is better, AAPL vs MSFT?") == "Comparison"

    def test_portfolio(self):
        """Detect portfolio keywords."""
        assert detect_action("How's my portfolio doing?") == "Portfolio"
        assert detect_action("Review my watchlist") == "Portfolio"

    def test_default_analysis(self):
        """Default to 'Analysis' when no keywords match."""
        assert detect_action("Tell me about AAPL") == "Analysis"
        assert detect_action("Random text here") == "Analysis"


class TestGenerateChatTitle:
    """Test chat title generation."""

    def test_single_symbol_with_action(self):
        """Generate title with symbol and detected action."""
        title = generate_chat_title("Show me AAPL technical indicators")
        assert title == "AAPL Technical Analysis"

    def test_single_symbol_default_action(self):
        """Generate title with symbol and default action."""
        title = generate_chat_title("Analyze NVDA stock")
        assert title == "NVDA Analysis"

    def test_multiple_symbols_comparison(self):
        """Generate comparison title for multiple symbols."""
        title = generate_chat_title("Compare GOOGL and META")
        assert title == "GOOGL vs META"

    def test_multiple_symbols_no_comparison(self):
        """Generate list title for multiple symbols without comparison."""
        title = generate_chat_title("Analyze AAPL, MSFT, NVDA earnings")
        assert "AAPL" in title
        assert "MSFT" in title

    def test_no_symbols_with_action(self):
        """Generate title from action when no symbols."""
        title = generate_chat_title("How's my portfolio doing?")
        assert title == "Portfolio"

    def test_no_symbols_fallback(self):
        """Generate fallback title when nothing detected."""
        title = generate_chat_title("Hello there")
        assert title == "Chat Analysis"

    def test_cash_flow_title(self):
        """Generate title for cash flow query."""
        title = generate_chat_title("What's the cash flow for MRVL?")
        assert title == "MRVL Cash Flow"

    def test_news_title(self):
        """Generate title for news query."""
        title = generate_chat_title("Latest news on TSLA")
        assert title == "TSLA News"

    def test_max_length_truncation(self):
        """Title is truncated to max length."""
        # Create a long message with multiple symbols
        title = generate_chat_title(
            "Compare AAPL, MSFT, GOOGL, META, NVDA, TSLA, AMD, INTC technical indicators"
        )
        assert len(title) <= MAX_TITLE_LENGTH

    def test_with_assistant_response(self):
        """Title generation includes assistant response context."""
        # The assistant response can provide additional symbol context
        title = generate_chat_title(
            "Analyze this stock",
            assistant_response="Based on AAPL's performance...",
        )
        # User message doesn't have symbol, but function uses combined text
        assert "Analysis" in title


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_message(self):
        """Empty message returns fallback title."""
        title = generate_chat_title("")
        assert title == "Chat Analysis"

    def test_none_response(self):
        """None assistant response is handled gracefully."""
        title = generate_chat_title("Analyze AAPL", None)
        assert title == "AAPL Analysis"

    def test_very_long_message(self):
        """Very long message doesn't cause issues."""
        long_message = "AAPL " * 1000
        title = generate_chat_title(long_message)
        assert len(title) <= MAX_TITLE_LENGTH
        assert "AAPL" in title

    def test_special_characters(self):
        """Special characters in message are handled."""
        title = generate_chat_title("What's AAPL's P/E ratio? (earnings)")
        assert "AAPL" in title

    def test_numbers_in_symbol(self):
        """Symbols with numbers in them (like 9988.HK) are tricky."""
        # Our pattern only matches letters, so this won't catch Hong Kong symbols
        symbols = extract_symbols("Analyze 9988.HK")
        assert "HK" in symbols  # Only the letters part matches


class TestExtractTitleFromResponse:
    """Test LLM-generated title extraction from responses."""

    def test_basic_extraction(self):
        """Extract title from properly formatted response."""
        response = "Analysis here...\n[chat_title: AAPL Analysis]"
        title, cleaned = extract_title_from_response(response)
        assert title == "AAPL Analysis"
        assert cleaned == "Analysis here..."

    def test_title_with_spaces(self):
        """Extract title with multiple words."""
        response = "Content\n[chat_title: NVDA Technical Analysis]"
        title, cleaned = extract_title_from_response(response)
        assert title == "NVDA Technical Analysis"
        assert cleaned == "Content"

    def test_case_insensitive(self):
        """Title pattern is case insensitive."""
        response = "Content\n[CHAT_TITLE: Market Overview]"
        title, cleaned = extract_title_from_response(response)
        assert title == "Market Overview"

    def test_no_title_found(self):
        """Return None if no title pattern found."""
        response = "Just regular content without title"
        title, cleaned = extract_title_from_response(response)
        assert title is None
        assert cleaned == response

    def test_empty_response(self):
        """Handle empty response gracefully."""
        title, cleaned = extract_title_from_response("")
        assert title is None
        assert cleaned == ""

    def test_none_response(self):
        """Handle None response gracefully."""
        title, cleaned = extract_title_from_response(None)
        assert title is None
        assert cleaned is None

    def test_title_truncation(self):
        """Long titles are truncated to 30 chars."""
        long_title = "This Is A Very Long Title That Exceeds Thirty Characters"
        response = f"Content\n[chat_title: {long_title}]"
        title, cleaned = extract_title_from_response(response)
        assert len(title) <= 30
        assert title.endswith("...")

    def test_title_with_trailing_whitespace(self):
        """Handle trailing whitespace in title."""
        response = "Content\n[chat_title:   AAPL Analysis   ]"
        title, cleaned = extract_title_from_response(response)
        assert title == "AAPL Analysis"

    def test_multiline_response(self):
        """Extract title from multiline response."""
        response = """This is a detailed analysis.

Key points:
- Point 1
- Point 2

[chat_title: TSLA News Summary]"""
        title, cleaned = extract_title_from_response(response)
        assert title == "TSLA News Summary"
        assert "Key points:" in cleaned
        assert "[chat_title:" not in cleaned

    def test_title_with_vs_comparison(self):
        """Extract comparison title."""
        response = "Comparison analysis...\n[chat_title: AAPL vs MSFT]"
        title, cleaned = extract_title_from_response(response)
        assert title == "AAPL vs MSFT"

    def test_title_not_at_end(self):
        """Title must be at the end of response."""
        response = "[chat_title: Should Not Match]\nMore content after"
        title, cleaned = extract_title_from_response(response)
        # Pattern requires title at end, so this should not match
        assert title is None
        assert cleaned == response
