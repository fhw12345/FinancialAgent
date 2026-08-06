"""
Market data formatting for Alpha Vantage responses.

Handles news sentiment, market movers, insider transactions, and ETF profiles.
"""

import typing
from datetime import datetime
from typing import Any

from .base import (
    format_large_number,
    generate_metadata_header,
    safe_float,
)


class MarketFormatter:
    """Formatter for market data responses."""

    @staticmethod
    def format_news_sentiment(
        raw_data: dict[str, Any], symbol: str, invoked_at: str
    ) -> str:
        """
        Format news sentiment with positive/negative articles.

        Args:
            raw_data: Raw Alpha Vantage NEWS_SENTIMENT response
            symbol: Stock symbol
            invoked_at: ISO timestamp

        Returns:
            Rich markdown with sentiment analysis
        """
        header = generate_metadata_header(
            tool_name="News Sentiment Analysis",
            symbol=symbol,
            invoked_at=invoked_at,
            data_source="NEWS_SENTIMENT",
        )

        feed = raw_data.get("feed", [])

        if not feed:
            return (
                f"{header}\n## News Sentiment - {symbol}\n\n"
                f"No news articles available for {symbol}"
            )

        # Filter by sentiment
        positive_news = [
            item for item in feed if item.get("overall_sentiment_score", 0) > 0.15
        ]
        negative_news = [
            item for item in feed if item.get("overall_sentiment_score", 0) < -0.15
        ]

        # Sort and limit
        positive_news = sorted(
            positive_news,
            key=lambda x: x.get("overall_sentiment_score", 0),
            reverse=True,
        )[:3]
        negative_news = sorted(
            negative_news, key=lambda x: x.get("overall_sentiment_score", 0)
        )[:3]

        output = [
            header,
            f"## News Sentiment - {symbol}",
            "",
            "### Overall Summary",
            f"Found {len(positive_news)} strongly positive and "
            f"{len(negative_news)} strongly negative articles",
            "",
        ]

        if positive_news:
            output.extend(["### Positive News", ""])
            for article in positive_news:
                MarketFormatter._format_news_article(output, article, "Bullish")

        if negative_news:
            output.extend(["### Negative News", ""])
            for article in negative_news:
                MarketFormatter._format_news_article(output, article, "Bearish")

        if not positive_news and not negative_news:
            output.append(
                "No strongly positive or negative articles found "
                "(sentiment threshold: +/-0.15)"
            )

        return "\n".join(output)

    @staticmethod
    def _format_news_article(
        output: list[str], article: dict[str, typing.Any], sentiment_label: str
    ) -> None:
        """Format a single news article."""
        score = article.get("overall_sentiment_score", 0)
        title = article.get("title", "")
        source = article.get("source", "Unknown")
        url = article.get("url", "#")
        summary = article.get("summary", "")
        time_published = article.get("time_published", "")

        # Format publication time
        time_str = ""
        if time_published:
            try:
                dt = datetime.strptime(time_published, "%Y%m%dT%H%M%S")
                time_str = f" - {dt.strftime('%b %d, %Y')}"
            except (ValueError, TypeError):
                pass

        # Title as clickable link
        output.append(f"🔗 **[{title}]({url})**")
        output.append(
            f"*{source}{time_str} - Sentiment: {score:+.2f} ({sentiment_label})*"
        )

        # Add summary if available
        if summary:
            output.extend(
                [
                    "",
                    "<details>",
                    "<summary><strong>📄 Read summary</strong></summary>",
                    "",
                    summary,
                    "",
                    "</details>",
                    "",
                ]
            )
        else:
            output.append("")

    @staticmethod
    def format_market_movers(raw_data: dict[str, Any], invoked_at: str) -> str:
        """
        Format market movers (gainers, losers, most active).

        Args:
            raw_data: Raw Alpha Vantage TOP_GAINERS_LOSERS response
            invoked_at: ISO timestamp

        Returns:
            Rich markdown with market movers
        """
        header = generate_metadata_header(
            tool_name="Market Movers",
            symbol=None,
            invoked_at=invoked_at,
            data_source="TOP_GAINERS_LOSERS",
        )

        gainers = raw_data.get("top_gainers", [])[:5]
        losers = raw_data.get("top_losers", [])[:5]
        active = raw_data.get("most_actively_traded", [])[:5]

        output = [
            header,
            "## Today's Market Movers",
            "",
        ]

        if gainers:
            output.extend(
                [
                    "### Top Gainers",
                    "",
                    "| Ticker | Price | Change | Volume |",
                    "|--------|-------|--------|--------|",
                ]
            )

            for stock in gainers:
                ticker = stock.get("ticker", "N/A")
                price = float(stock.get("price", 0))
                change_pct = stock.get("change_percentage", "N/A")
                volume = int(stock.get("volume", 0))

                output.append(
                    f"| {ticker} | ${price:.2f} | {change_pct} | {volume / 1e6:.1f}M |"
                )

            output.append("")

        if losers:
            output.extend(
                [
                    "### Top Losers",
                    "",
                    "| Ticker | Price | Change | Volume |",
                    "|--------|-------|--------|--------|",
                ]
            )

            for stock in losers:
                ticker = stock.get("ticker", "N/A")
                price = float(stock.get("price", 0))
                change_pct = stock.get("change_percentage", "N/A")
                volume = int(stock.get("volume", 0))

                output.append(
                    f"| {ticker} | ${price:.2f} | {change_pct} | {volume / 1e6:.1f}M |"
                )

            output.append("")

        if active:
            output.extend(
                [
                    "### Most Active",
                    "",
                    "| Ticker | Price | Change | Volume |",
                    "|--------|-------|--------|--------|",
                ]
            )

            for stock in active:
                ticker = stock.get("ticker", "N/A")
                price = float(stock.get("price", 0))
                change_pct = stock.get("change_percentage", "N/A")
                volume = int(stock.get("volume", 0))

                output.append(
                    f"| {ticker} | ${price:.2f} | {change_pct} | {volume / 1e6:.1f}M |"
                )

        return "\n".join(output)

    @staticmethod
    def format_insider_transactions(
        raw_data: dict[str, Any],
        symbol: str,
        invoked_at: str,
    ) -> str:
        """
        Format insider transactions for LLM consumption.

        Groups by acquisition vs disposal, shows recent activity trends.

        Args:
            raw_data: Dict with 'data' list of transaction records
            symbol: Stock symbol
            invoked_at: Timestamp when tool was invoked

        Returns:
            Compressed markdown summary of insider activity
        """
        output = [
            f"# Insider Transactions: {symbol}",
            f"*Data Source: Alpha Vantage | Invoked: {invoked_at}*",
            "",
        ]

        transactions = raw_data.get("data", [])

        if not transactions:
            output.append("**No insider transaction data available**")
            return "\n".join(output)

        # Group by acquisition vs disposal
        acquisitions = [
            t for t in transactions if t.get("acquisition_or_disposal") == "A"
        ]
        disposals = [t for t in transactions if t.get("acquisition_or_disposal") == "D"]

        # Calculate totals
        total_acquired_shares = sum(
            safe_float(t.get("shares", "0")) for t in acquisitions
        )
        total_disposed_shares = sum(safe_float(t.get("shares", "0")) for t in disposals)

        output.extend(
            [
                "## Recent Activity Summary",
                "",
                f"- **Acquisitions**: {len(acquisitions)} transactions "
                f"({total_acquired_shares:,.0f} shares)",
                f"- **Disposals**: {len(disposals)} transactions "
                f"({total_disposed_shares:,.0f} shares)",
                "",
            ]
        )

        # Trend analysis
        net_shares = total_acquired_shares - total_disposed_shares
        if net_shares > 0:
            trend = f"**Bullish** (Net buying: {net_shares:,.0f} shares)"
        elif net_shares < 0:
            trend = f"**Bearish** (Net selling: {abs(net_shares):,.0f} shares)"
        else:
            trend = "**Neutral** (No net change)"

        output.extend([f"**Insider Sentiment**: {trend}", ""])

        # Top acquisitions
        if acquisitions:
            output.extend(
                [
                    "### Top Acquisitions",
                    "",
                    "| Date | Executive | Shares | Price |",
                    "|------|-----------|--------|-------|",
                ]
            )

            for t in acquisitions[:5]:
                date = t.get("transaction_date", "N/A")
                exec_name = t.get("executive", "N/A")
                shares = safe_float(t.get("shares", "0"))
                price = safe_float(t.get("share_price", "0"))

                output.append(
                    f"| {date} | {exec_name[:25]} | {shares:,.0f} | ${price:.2f} |"
                )

            output.append("")

        # Top disposals
        if disposals:
            output.extend(
                [
                    "### Top Disposals",
                    "",
                    "| Date | Executive | Shares | Price |",
                    "|------|-----------|--------|-------|",
                ]
            )

            for t in disposals[:5]:
                date = t.get("transaction_date", "N/A")
                exec_name = t.get("executive", "N/A")
                shares = safe_float(t.get("shares", "0"))
                price = safe_float(t.get("share_price", "0"))

                output.append(
                    f"| {date} | {exec_name[:25]} | {shares:,.0f} | ${price:.2f} |"
                )

            output.append("")

        return "\n".join(output)

    @staticmethod
    def format_etf_profile(
        raw_data: dict[str, Any],
        symbol: str,
        invoked_at: str,
    ) -> str:
        """
        Format ETF profile with top holdings and sector allocation.

        Args:
            raw_data: Dict with ETF profile data
            symbol: ETF ticker symbol
            invoked_at: Timestamp when tool was invoked

        Returns:
            Formatted ETF profile markdown
        """
        output = [
            f"# ETF Profile: {symbol}",
            f"*Data Source: Alpha Vantage | Invoked: {invoked_at}*",
            "",
        ]

        # Overview
        net_assets = raw_data.get("net_assets", "N/A")
        expense_ratio = raw_data.get("net_expense_ratio", "N/A")
        dividend_yield = raw_data.get("dividend_yield", "N/A")
        leveraged = raw_data.get("leveraged", "NO")

        # Format net assets
        if net_assets != "N/A":
            net_assets_num = safe_float(net_assets)
            net_assets_formatted = format_large_number(net_assets_num)
        else:
            net_assets_formatted = "N/A"

        output.extend(
            [
                "## Overview",
                "",
                f"- **Net Assets**: ${net_assets_formatted}",
                f"- **Expense Ratio**: {expense_ratio}",
                f"- **Dividend Yield**: {dividend_yield}",
                f"- **Leveraged**: {leveraged}",
                "",
            ]
        )

        # Top holdings
        holdings = raw_data.get("holdings", [])
        if holdings:
            output.extend(
                [
                    f"## Top {min(10, len(holdings))} Holdings",
                    "",
                    "| Symbol | Description | Weight |",
                    "|--------|-------------|--------|",
                ]
            )

            for holding in holdings[:10]:
                symbol_h = holding.get("symbol", "N/A")
                desc = holding.get("description", "N/A")
                weight = holding.get("weight", "0")
                weight_pct = safe_float(weight) * 100

                output.append(f"| {symbol_h} | {desc[:30]} | {weight_pct:.2f}% |")

            output.append("")

        # Sector allocation
        sectors = raw_data.get("sectors", [])
        if sectors:
            output.extend(
                [
                    "## Sector Allocation",
                    "",
                    "| Sector | Weight |",
                    "|--------|--------|",
                ]
            )

            for sector in sectors:
                sector_name = sector.get("sector", "N/A")
                weight = sector.get("weight", "0")
                weight_pct = safe_float(weight) * 100

                output.append(f"| {sector_name} | {weight_pct:.2f}% |")

            output.append("")

        return "\n".join(output)
