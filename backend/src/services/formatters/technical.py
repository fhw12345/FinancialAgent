"""
Technical data formatting for Alpha Vantage responses.

Handles commodity prices and technical indicators.
"""

from typing import Any


class TechnicalFormatter:
    """Formatter for technical analysis data."""

    @staticmethod
    def format_commodity_price(
        df: Any,  # pd.DataFrame
        commodity: str,
        interval: str,
        invoked_at: str,
    ) -> str:
        """
        Format commodity price data with trend analysis.

        Args:
            df: DataFrame with date index and value column
            commodity: Commodity name (e.g., "COPPER")
            interval: Price interval
            invoked_at: Timestamp when tool was invoked

        Returns:
            Formatted commodity price markdown with trends
        """
        output = [
            f"# {commodity.title()} Prices ({interval.title()})",
            f"*Data Source: Alpha Vantage | Invoked: {invoked_at}*",
            "",
        ]

        if df.empty:
            output.append("**No price data available**")
            return "\n".join(output)

        # Current price (most recent)
        current_price = float(df.iloc[-1]["value"])

        output.extend(
            [
                f"## Current Price: ${current_price:,.2f}",
                "",
            ]
        )

        # Calculate trends (if enough data)
        if len(df) >= 12:
            price_1m_ago = (
                float(df.iloc[-2]["value"]) if len(df) >= 2 else current_price
            )
            price_3m_ago = (
                float(df.iloc[-4]["value"]) if len(df) >= 4 else current_price
            )
            price_12m_ago = (
                float(df.iloc[-13]["value"]) if len(df) >= 13 else current_price
            )

            change_1m = ((current_price - price_1m_ago) / price_1m_ago) * 100
            change_3m = ((current_price - price_3m_ago) / price_3m_ago) * 100
            change_12m = ((current_price - price_12m_ago) / price_12m_ago) * 100

            output.extend(
                [
                    "## Trend Analysis",
                    "",
                    f"- **1-Period Change**: {change_1m:+.1f}% "
                    f"(${price_1m_ago:,.2f} -> ${current_price:,.2f})",
                    f"- **3-Period Change**: {change_3m:+.1f}% "
                    f"(${price_3m_ago:,.2f} -> ${current_price:,.2f})",
                    f"- **12-Period Change**: {change_12m:+.1f}% "
                    f"(${price_12m_ago:,.2f} -> ${current_price:,.2f})",
                    "",
                ]
            )

            # Overall trend
            if change_12m > 10:
                trend = "**Strong Bullish** (Rising demand)"
            elif change_12m > 0:
                trend = "**Bullish** (Moderate growth)"
            elif change_12m > -10:
                trend = "**Bearish** (Slight decline)"
            else:
                trend = "**Strong Bearish** (Falling demand)"

            output.extend([f"**Overall Trend**: {trend}", ""])

        # Recent price history (last 12 periods)
        output.extend(
            [
                "## Price History (Recent)",
                "",
                "| Date | Price | Change |",
                "|------|-------|--------|",
            ]
        )

        recent_df = df.tail(12)
        for i, (date, row) in enumerate(recent_df.iterrows()):
            price = float(row["value"])
            if i > 0:
                prev_price = float(recent_df.iloc[i - 1]["value"])
                change_pct = ((price - prev_price) / prev_price) * 100
                change_str = f"{change_pct:+.1f}%"
            else:
                change_str = "-"

            output.append(f"| {date.date()} | ${price:,.2f} | {change_str} |")

        output.append("")

        return "\n".join(output)

    @staticmethod
    def format_technical_indicator(
        df: Any,  # pd.DataFrame
        symbol: str,
        function: str,
        interval: str,
        invoked_at: str,
        data_source: str = "yfinance_local",
    ) -> str:
        """
        Format technical indicator with current value and signal.

        Args:
            df: DataFrame with indicator values
            symbol: Stock symbol
            function: Indicator name (RSI, MACD, etc.)
            interval: Time interval
            invoked_at: Timestamp when tool was invoked
            data_source: Where the indicator was computed.
                "yfinance_local" — pandas-ta on yfinance bars (default, primary path).
                "alpha_vantage_fallback" — AV's TECHNICAL_INDICATOR endpoint
                (used only when yfinance fails).

        Returns:
            Formatted technical indicator markdown
        """
        output = [
            f"# {function}: {symbol}",
            f"*{interval.title()} | Data Source: {data_source} | Invoked: {invoked_at}*",
            "",
        ]

        if df.empty:
            output.append("**No indicator data available**")
            return "\n".join(output)

        # Current value (most recent)
        last_row = df.iloc[-1]

        # Format current value based on indicator type
        if len(df.columns) == 1:
            # Single-value indicators (SMA, EMA, RSI, etc.)
            col_name = df.columns[0]
            current_value = float(last_row[col_name])

            output.extend(
                [
                    f"## Current {function}: {current_value:.2f}",
                    "",
                ]
            )

            # Add signal interpretation for specific indicators
            if function == "RSI":
                if current_value > 70:
                    signal = "**Overbought** (Potential reversal down)"
                elif current_value < 30:
                    signal = "**Oversold** (Potential reversal up)"
                else:
                    signal = "**Neutral** (Range-bound)"

                output.extend([f"**Signal**: {signal}", ""])

        else:
            # Multi-value indicators (MACD, STOCH, BBANDS, etc.)
            output.extend(["## Current Values", ""])

            for col in df.columns:
                value = float(last_row[col])
                output.append(f"- **{col}**: {value:.2f}")

            output.append("")

            # MACD-specific signal
            if function == "MACD" and "MACD" in df.columns:
                macd_val = float(last_row.get("MACD", 0))
                signal_val = float(last_row.get("MACD_Signal", 0))

                if macd_val > signal_val:
                    signal = "**Bullish** (MACD above signal)"
                else:
                    signal = "**Bearish** (MACD below signal)"

                output.extend([f"**Signal**: {signal}", ""])

        # Recent values table (last 10 periods)
        output.extend(
            [
                "## Recent Values",
                "",
            ]
        )

        # Build table header
        header = "| Date |"
        separator = "|------|"
        for col in df.columns:
            header += f" {col} |"
            separator += "--------|"

        output.extend([header, separator])

        # Add last 10 rows
        recent_df = df.tail(10)
        for date, row in recent_df.iterrows():
            row_str = f"| {date.date() if hasattr(date, 'date') else date} |"
            for col in df.columns:
                value = float(row[col])
                row_str += f" {value:.2f} |"
            output.append(row_str)

        output.append("")

        return "\n".join(output)
