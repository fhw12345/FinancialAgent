"""
Unit tests for MarketFormatter.

Tests news sentiment, market movers, insider transactions, and ETF profile formatting.
"""

from src.services.formatters.market import MarketFormatter

# ===== format_news_sentiment Tests =====


class TestFormatNewsSentiment:
    """Test format_news_sentiment method"""

    def test_format_with_positive_and_negative_news(self):
        """Test formatting with both positive and negative news"""
        raw_data = {
            "feed": [
                {
                    "title": "Stock Surges on Strong Earnings",
                    "overall_sentiment_score": 0.5,
                    "source": "MarketWatch",
                    "url": "https://example.com/news1",
                    "summary": "Great earnings report",
                    "time_published": "20250110T140000",
                },
                {
                    "title": "Company Faces Lawsuit",
                    "overall_sentiment_score": -0.4,
                    "source": "Reuters",
                    "url": "https://example.com/news2",
                    "summary": "Legal troubles ahead",
                    "time_published": "20250110T120000",
                },
            ]
        }

        result = MarketFormatter.format_news_sentiment(
            raw_data=raw_data,
            symbol="AAPL",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "News Sentiment - AAPL" in result
        assert "Overall Summary" in result
        assert "Positive News" in result
        assert "Negative News" in result
        assert "Stock Surges on Strong Earnings" in result
        assert "Company Faces Lawsuit" in result
        assert "Bullish" in result
        assert "Bearish" in result

    def test_format_empty_feed(self):
        """Test formatting with no news"""
        raw_data = {"feed": []}

        result = MarketFormatter.format_news_sentiment(
            raw_data=raw_data,
            symbol="AAPL",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "No news articles available for AAPL" in result

    def test_format_neutral_news_only(self):
        """Test formatting with only neutral news"""
        raw_data = {
            "feed": [
                {
                    "title": "Company Reports Q4 Results",
                    "overall_sentiment_score": 0.05,  # Neutral (within +/-0.15)
                    "source": "Bloomberg",
                    "url": "https://example.com/news1",
                },
                {
                    "title": "Market Update",
                    "overall_sentiment_score": -0.10,  # Neutral
                    "source": "CNBC",
                    "url": "https://example.com/news2",
                },
            ]
        }

        result = MarketFormatter.format_news_sentiment(
            raw_data=raw_data,
            symbol="MSFT",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "No strongly positive or negative articles found" in result
        assert "threshold: +/-0.15" in result

    def test_format_with_missing_fields(self):
        """Test formatting handles missing fields gracefully"""
        raw_data = {
            "feed": [
                {
                    "title": "Test Article",
                    "overall_sentiment_score": 0.3,
                    # Missing source, url, summary, time_published
                },
            ]
        }

        result = MarketFormatter.format_news_sentiment(
            raw_data=raw_data,
            symbol="GOOGL",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "Test Article" in result
        assert "Unknown" in result  # Default source

    def test_format_article_with_bad_date(self):
        """Test article with invalid date format"""
        raw_data = {
            "feed": [
                {
                    "title": "Stock News",
                    "overall_sentiment_score": 0.25,
                    "source": "MarketWatch",
                    "url": "https://example.com",
                    "time_published": "invalid-date",
                },
            ]
        }

        result = MarketFormatter.format_news_sentiment(
            raw_data=raw_data,
            symbol="AAPL",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "Stock News" in result  # Should still format without date

    def test_format_limits_articles(self):
        """Test that only top 3 positive/negative articles are shown"""
        # Create 5 positive and 5 negative articles
        positive_articles = [
            {
                "title": f"GoodStory{i}",
                "overall_sentiment_score": 0.2 + i * 0.1,
                "source": "Source",
                "url": f"https://example.com/pos{i}",
            }
            for i in range(5)
        ]

        negative_articles = [
            {
                "title": f"BadStory{i}",
                "overall_sentiment_score": -0.2 - i * 0.1,
                "source": "Source",
                "url": f"https://example.com/neg{i}",
            }
            for i in range(5)
        ]

        raw_data = {"feed": positive_articles + negative_articles}

        result = MarketFormatter.format_news_sentiment(
            raw_data=raw_data,
            symbol="AAPL",
            invoked_at="2025-01-10T12:00:00Z",
        )

        # Should only have 3 of each shown (counting unique titles)
        assert result.count("GoodStory") == 3
        assert result.count("BadStory") == 3


# ===== format_market_movers Tests =====


class TestFormatMarketMovers:
    """Test format_market_movers method"""

    def test_format_all_categories(self):
        """Test formatting with gainers, losers, and active"""
        raw_data = {
            "top_gainers": [
                {
                    "ticker": "AAPL",
                    "price": "150.00",
                    "change_percentage": "+5%",
                    "volume": "10000000",
                },
                {
                    "ticker": "MSFT",
                    "price": "300.00",
                    "change_percentage": "+3%",
                    "volume": "8000000",
                },
            ],
            "top_losers": [
                {
                    "ticker": "META",
                    "price": "200.00",
                    "change_percentage": "-4%",
                    "volume": "5000000",
                },
            ],
            "most_actively_traded": [
                {
                    "ticker": "TSLA",
                    "price": "250.00",
                    "change_percentage": "+1%",
                    "volume": "20000000",
                },
            ],
        }

        result = MarketFormatter.format_market_movers(
            raw_data=raw_data,
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "Today's Market Movers" in result
        assert "Top Gainers" in result
        assert "Top Losers" in result
        assert "Most Active" in result
        assert "AAPL" in result
        assert "$150.00" in result
        assert "META" in result
        assert "TSLA" in result

    def test_format_only_gainers(self):
        """Test formatting with only gainers"""
        raw_data = {
            "top_gainers": [
                {
                    "ticker": "AAPL",
                    "price": "150.00",
                    "change_percentage": "+5%",
                    "volume": "10000000",
                },
            ],
            "top_losers": [],
            "most_actively_traded": [],
        }

        result = MarketFormatter.format_market_movers(
            raw_data=raw_data,
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "Top Gainers" in result
        assert "Top Losers" not in result
        assert "Most Active" not in result

    def test_format_empty_data(self):
        """Test formatting with no data"""
        raw_data = {}

        result = MarketFormatter.format_market_movers(
            raw_data=raw_data,
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "Today's Market Movers" in result
        assert "| Ticker" not in result  # No table rows

    def test_format_volume_formatting(self):
        """Test volume is formatted in millions"""
        raw_data = {
            "top_gainers": [
                {
                    "ticker": "AAPL",
                    "price": "150.00",
                    "change_percentage": "+5%",
                    "volume": "15000000",
                },
            ],
            "top_losers": [],
            "most_actively_traded": [],
        }

        result = MarketFormatter.format_market_movers(
            raw_data=raw_data,
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "15.0M" in result

    def test_format_limits_to_five(self):
        """Test that only top 5 are shown in each category"""
        raw_data = {
            "top_gainers": [
                {
                    "ticker": f"STOCK{i}",
                    "price": "100.00",
                    "change_percentage": "+1%",
                    "volume": "1000000",
                }
                for i in range(10)
            ],
            "top_losers": [],
            "most_actively_traded": [],
        }

        result = MarketFormatter.format_market_movers(
            raw_data=raw_data,
            invoked_at="2025-01-10T12:00:00Z",
        )

        # Count table rows in gainers section
        assert result.count("STOCK") == 5


# ===== format_insider_transactions Tests =====


class TestFormatInsiderTransactions:
    """Test format_insider_transactions method"""

    def test_format_acquisitions_and_disposals(self):
        """Test formatting with both acquisitions and disposals"""
        raw_data = {
            "data": [
                {
                    "acquisition_or_disposal": "A",
                    "transaction_date": "2025-01-05",
                    "executive": "Tim Cook",
                    "shares": "10000",
                    "share_price": "150.00",
                },
                {
                    "acquisition_or_disposal": "D",
                    "transaction_date": "2025-01-04",
                    "executive": "Jeff Williams",
                    "shares": "5000",
                    "share_price": "148.00",
                },
            ]
        }

        result = MarketFormatter.format_insider_transactions(
            raw_data=raw_data,
            symbol="AAPL",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "Insider Transactions: AAPL" in result
        assert "Acquisitions" in result
        assert "Disposals" in result
        assert "Tim Cook" in result
        assert "Jeff Williams" in result
        assert "10,000" in result
        assert "5,000" in result

    def test_format_net_buying_bullish(self):
        """Test bullish sentiment with net buying"""
        raw_data = {
            "data": [
                {
                    "acquisition_or_disposal": "A",
                    "shares": "10000",
                    "transaction_date": "2025-01-05",
                    "executive": "CEO",
                    "share_price": "100.00",
                },
                {
                    "acquisition_or_disposal": "D",
                    "shares": "3000",
                    "transaction_date": "2025-01-04",
                    "executive": "CFO",
                    "share_price": "100.00",
                },
            ]
        }

        result = MarketFormatter.format_insider_transactions(
            raw_data=raw_data,
            symbol="AAPL",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "**Bullish**" in result
        assert "Net buying" in result

    def test_format_net_selling_bearish(self):
        """Test bearish sentiment with net selling"""
        raw_data = {
            "data": [
                {
                    "acquisition_or_disposal": "A",
                    "shares": "5000",
                    "transaction_date": "2025-01-05",
                    "executive": "CEO",
                    "share_price": "100.00",
                },
                {
                    "acquisition_or_disposal": "D",
                    "shares": "15000",
                    "transaction_date": "2025-01-04",
                    "executive": "CFO",
                    "share_price": "100.00",
                },
            ]
        }

        result = MarketFormatter.format_insider_transactions(
            raw_data=raw_data,
            symbol="AAPL",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "**Bearish**" in result
        assert "Net selling" in result

    def test_format_neutral_sentiment(self):
        """Test neutral sentiment with no net change"""
        raw_data = {
            "data": [
                {
                    "acquisition_or_disposal": "A",
                    "shares": "5000",
                    "transaction_date": "2025-01-05",
                    "executive": "CEO",
                    "share_price": "100.00",
                },
                {
                    "acquisition_or_disposal": "D",
                    "shares": "5000",
                    "transaction_date": "2025-01-04",
                    "executive": "CFO",
                    "share_price": "100.00",
                },
            ]
        }

        result = MarketFormatter.format_insider_transactions(
            raw_data=raw_data,
            symbol="AAPL",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "**Neutral**" in result

    def test_format_empty_transactions(self):
        """Test formatting with no transactions"""
        raw_data = {"data": []}

        result = MarketFormatter.format_insider_transactions(
            raw_data=raw_data,
            symbol="AAPL",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "No insider transaction data available" in result

    def test_format_long_executive_name_truncated(self):
        """Test long executive names are truncated"""
        raw_data = {
            "data": [
                {
                    "acquisition_or_disposal": "A",
                    "transaction_date": "2025-01-05",
                    "executive": "Very Long Executive Name That Should Be Truncated",
                    "shares": "10000",
                    "share_price": "100.00",
                },
            ]
        }

        result = MarketFormatter.format_insider_transactions(
            raw_data=raw_data,
            symbol="AAPL",
            invoked_at="2025-01-10T12:00:00Z",
        )

        # Name should be truncated to 25 chars
        assert "Very Long Executive Name " in result
        assert "Should Be Truncated" not in result


# ===== format_etf_profile Tests =====


class TestFormatEtfProfile:
    """Test format_etf_profile method"""

    def test_format_complete_profile(self):
        """Test formatting complete ETF profile"""
        raw_data = {
            "net_assets": "1000000000",
            "net_expense_ratio": "0.03%",
            "dividend_yield": "1.5%",
            "leveraged": "NO",
            "holdings": [
                {"symbol": "AAPL", "description": "Apple Inc", "weight": "0.10"},
                {"symbol": "MSFT", "description": "Microsoft Corp", "weight": "0.08"},
            ],
            "sectors": [
                {"sector": "Technology", "weight": "0.35"},
                {"sector": "Healthcare", "weight": "0.15"},
            ],
        }

        result = MarketFormatter.format_etf_profile(
            raw_data=raw_data,
            symbol="SPY",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "ETF Profile: SPY" in result
        assert "Overview" in result
        assert "Net Assets" in result
        assert "1.00B" in result  # Formatted as billions
        assert "Expense Ratio" in result
        assert "Dividend Yield" in result
        assert "Top" in result
        assert "Holdings" in result
        assert "AAPL" in result
        assert "10.00%" in result  # Weight formatted as percentage
        assert "Sector Allocation" in result
        assert "Technology" in result

    def test_format_profile_no_holdings(self):
        """Test formatting ETF with no holdings"""
        raw_data = {
            "net_assets": "500000000",
            "net_expense_ratio": "0.05%",
            "dividend_yield": "2.0%",
            "leveraged": "YES",
        }

        result = MarketFormatter.format_etf_profile(
            raw_data=raw_data,
            symbol="QQQ",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "ETF Profile: QQQ" in result
        assert "Overview" in result
        assert "YES" in result  # Leveraged
        assert "Holdings" not in result  # No holdings section

    def test_format_profile_no_sectors(self):
        """Test formatting ETF with no sector data"""
        raw_data = {
            "net_assets": "500000000",
            "net_expense_ratio": "0.05%",
            "holdings": [
                {"symbol": "AAPL", "description": "Apple Inc", "weight": "0.10"},
            ],
        }

        result = MarketFormatter.format_etf_profile(
            raw_data=raw_data,
            symbol="QQQ",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "Holdings" in result
        assert "Sector Allocation" not in result

    def test_format_profile_limits_holdings(self):
        """Test that only top 10 holdings are shown"""
        holdings = [
            {"symbol": f"SYM{i}", "description": f"Company {i}", "weight": "0.05"}
            for i in range(15)
        ]

        raw_data = {
            "net_assets": "1000000000",
            "holdings": holdings,
        }

        result = MarketFormatter.format_etf_profile(
            raw_data=raw_data,
            symbol="SPY",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "Top 10 Holdings" in result
        assert result.count("SYM") == 10

    def test_format_profile_na_values(self):
        """Test formatting with N/A values"""
        raw_data = {}

        result = MarketFormatter.format_etf_profile(
            raw_data=raw_data,
            symbol="XYZ",
            invoked_at="2025-01-10T12:00:00Z",
        )

        assert "N/A" in result  # Net assets should be N/A
