"""
Fundamentals formatting for Alpha Vantage responses.

Handles company overview, cash flow, and balance sheet formatting.
"""

from typing import Any

from .base import (
    calculate_qoq_growth,
    format_large_number,
    generate_metadata_header,
    safe_float,
)


class FundamentalsFormatter:
    """Formatter for company fundamentals data."""

    @staticmethod
    def format_company_overview(
        raw_data: dict[str, Any], symbol: str, invoked_at: str
    ) -> str:
        """
        Format company overview with comprehensive metrics.

        Args:
            raw_data: Raw Alpha Vantage OVERVIEW response
            symbol: Stock symbol
            invoked_at: ISO timestamp

        Returns:
            Rich markdown with company info and key metrics
        """
        header = generate_metadata_header(
            tool_name="Company Overview",
            symbol=symbol,
            invoked_at=invoked_at,
            data_source="OVERVIEW",
        )

        # Extract company info
        name = raw_data.get("Name", symbol)
        description = raw_data.get("Description", "N/A")
        industry = raw_data.get("Industry", "N/A")
        sector = raw_data.get("Sector", "N/A")
        exchange = raw_data.get("Exchange", "N/A")
        country = raw_data.get("Country", "N/A")

        # Extract key metrics
        market_cap = safe_float(raw_data.get("MarketCapitalization"))
        pe_ratio = safe_float(raw_data.get("PERatio"))
        eps = safe_float(raw_data.get("EPS"))
        profit_margin = safe_float(raw_data.get("ProfitMargin")) * 100
        revenue_ttm = safe_float(raw_data.get("RevenueTTM"))
        dividend_yield = safe_float(raw_data.get("DividendYield")) * 100
        beta = safe_float(raw_data.get("Beta"))
        percent_insiders = safe_float(raw_data.get("PercentInsiders"))
        percent_institutions = safe_float(raw_data.get("PercentInstitutions"))
        week_52_high = safe_float(raw_data.get("52WeekHigh"))
        week_52_low = safe_float(raw_data.get("52WeekLow"))

        # Build output
        output = [
            header,
            f"## Company Overview - {symbol}",
            f"*{name}*",
            "",
            "### Company Information",
            "",
            f"**Industry:** {industry} | **Sector:** {sector}",
            f"**Exchange:** {exchange} | **Country:** {country}",
            "",
            f"**Description:** {description}",
            "",
            "### Key Metrics",
            "",
            "| Metric | Value | Metric | Value |",
            "|--------|-------|--------|-------|",
        ]

        # Build metrics table (2 columns)
        metrics = []
        if market_cap > 0:
            metrics.append(
                (
                    f"Market Cap | {format_large_number(market_cap)}",
                    (
                        f"P/E Ratio | {pe_ratio:.2f}"
                        if pe_ratio > 0
                        else "P/E Ratio | N/A"
                    ),
                )
            )
        if eps != 0:
            metrics.append(
                (
                    f"EPS | ${eps:.2f}",
                    (
                        f"Profit Margin | {profit_margin:.2f}%"
                        if profit_margin > 0
                        else "Profit Margin | N/A"
                    ),
                )
            )
        if revenue_ttm > 0:
            metrics.append(
                (
                    f"Revenue (TTM) | {format_large_number(revenue_ttm)}",
                    (
                        f"Dividend Yield | {dividend_yield:.2f}%"
                        if dividend_yield > 0
                        else "Dividend Yield | N/A"
                    ),
                )
            )
        if beta != 0:
            metrics.append(
                (
                    f"Beta | {beta:.2f}",
                    (
                        f"% Insiders | {percent_insiders:.2f}%"
                        if percent_insiders > 0
                        else "% Insiders | N/A"
                    ),
                )
            )
        if percent_institutions > 0:
            metrics.append(
                (
                    f"% Institutions | {percent_institutions:.2f}%",
                    (
                        f"52W High | ${week_52_high:.2f}"
                        if week_52_high > 0
                        else "52W High | N/A"
                    ),
                )
            )
        if week_52_low > 0:
            metrics.append(("52W Low | $" + f"{week_52_low:.2f}", "- | -"))

        # Add metrics to table
        for left, right in metrics:
            output.append(f"| {left} | {right} |")

        return "\n".join(output)

    @staticmethod
    def format_earnings(
        raw_data: dict[str, Any],
        symbol: str,
        invoked_at: str,
        quarterly_count: int = 8,
    ) -> str:
        """
        Format earnings data with beat/miss analysis.

        Args:
            raw_data: Raw Alpha Vantage EARNINGS response
            symbol: Stock symbol
            invoked_at: ISO timestamp
            quarterly_count: Number of quarterly reports to show (default: 8)

        Returns:
            Rich markdown with earnings history and beat/miss analysis
        """
        header = generate_metadata_header(
            tool_name="Earnings Analysis",
            symbol=symbol,
            invoked_at=invoked_at,
            data_source="EARNINGS",
        )

        annual_earnings = raw_data.get("annualEarnings", [])
        quarterly_earnings = raw_data.get("quarterlyEarnings", [])

        output = [
            header,
            f"## Earnings - {symbol}",
            "",
        ]

        # Quarterly earnings table (most useful for beat/miss)
        quarters = quarterly_earnings[:quarterly_count]
        if quarters:
            output.extend([
                f"### Quarterly EPS (Last {len(quarters)} Quarters)",
                "",
                "| Report Date | Reported EPS | Estimated EPS | Surprise | Surprise % |",
                "|-------------|-------------|---------------|----------|------------|",
            ])

            beats = 0
            misses = 0
            surprise_pcts = []

            for q in quarters:
                reported = safe_float(q.get("reportedEPS"))
                estimated = safe_float(q.get("estimatedEPS"))
                surprise = safe_float(q.get("surprise"))
                surprise_pct = safe_float(q.get("surprisePercentage"))
                report_date = q.get("reportedDate", q.get("fiscalDateEnding", "N/A"))

                if surprise > 0:
                    beats += 1
                    indicator = "Beat"
                elif surprise < 0:
                    misses += 1
                    indicator = "Miss"
                else:
                    indicator = "In-line"

                surprise_pcts.append(surprise_pct)

                output.append(
                    f"| {report_date} | ${reported:.2f} | "
                    f"${estimated:.2f} | "
                    f"${surprise:+.2f} ({indicator}) | "
                    f"{surprise_pct:+.1f}% |"
                )

            # Beat/miss summary
            total = beats + misses + (len(quarters) - beats - misses)
            avg_surprise = (
                sum(surprise_pcts) / len(surprise_pcts) if surprise_pcts else 0
            )
            output.extend([
                "",
                "### Beat/Miss Summary",
                f"* **Beat Rate:** {beats}/{total} quarters ({beats/total*100:.0f}%)"
                if total > 0
                else "* **Beat Rate:** N/A",
                f"* **Average Surprise:** {avg_surprise:+.1f}%",
                f"* **Beats:** {beats} | **Misses:** {misses} | "
                f"**In-line:** {total - beats - misses}",
            ])

        # Annual earnings (compact)
        annual = annual_earnings[:5]
        if annual:
            output.extend([
                "",
                "### Annual EPS",
                "",
                "| Fiscal Year | Reported EPS |",
                "|-------------|-------------|",
            ])

            for a in annual:
                fiscal_date = a.get("fiscalDateEnding", "N/A")
                reported = safe_float(a.get("reportedEPS"))
                output.append(f"| {fiscal_date} | ${reported:.2f} |")

            # YoY growth if at least 2 years
            if len(annual) >= 2:
                latest = safe_float(annual[0].get("reportedEPS"))
                previous = safe_float(annual[1].get("reportedEPS"))
                growth = calculate_qoq_growth(latest, previous)
                output.extend([
                    "",
                    f"* **EPS YoY Growth:** {growth}",
                ])

        return "\n".join(output)

    @staticmethod
    def format_cash_flow(
        raw_data: dict[str, Any],
        symbol: str,
        invoked_at: str,
        count: int = 3,
        period: str = "quarter",
    ) -> str:
        """
        Format cash flow statement with configurable period selection.

        Args:
            raw_data: Raw Alpha Vantage CASH_FLOW response
            symbol: Stock symbol
            invoked_at: ISO timestamp
            count: Number of periods to return (default: 3)
            period: "quarter" for quarterly, "year" for annual (default: "quarter")

        Returns:
            Rich markdown with cash flow data for specified periods
        """
        header = generate_metadata_header(
            tool_name="Cash Flow Analysis",
            symbol=symbol,
            invoked_at=invoked_at,
            data_source="CASH_FLOW",
        )

        annual_reports = raw_data.get("annualReports", [])
        quarterly_reports = raw_data.get("quarterlyReports", [])

        # Select data based on period type
        if period == "year":
            reports = annual_reports[:count]
            period_label = f"Latest {count} Annual" if count > 1 else "Latest Annual"
        else:
            reports = quarterly_reports[:count]
            period_label = f"Latest {count} Quarters" if count > 1 else "Latest Quarter"

        if not reports:
            return (
                f"{header}\n## Cash Flow - {symbol}\n\n"
                f"No cash flow data available for {symbol}"
            )

        output = [
            header,
            f"## Cash Flow - {symbol}",
            "",
            f"### {period_label}",
            "",
        ]

        # Multi-period table format
        if period == "quarter":
            output.extend(
                [
                    "| Quarter End | Operating CF | CapEx | Free CF | Net Income |",
                    "|-------------|--------------|-------|---------|------------|",
                ]
            )
        else:
            output.extend(
                [
                    "| Fiscal Year | Operating CF | CapEx | Free CF | Net Income |",
                    "|-------------|--------------|-------|---------|------------|",
                ]
            )

        # Track for trend analysis
        fcf_values = []

        for report in reports:
            date_ending = report.get("fiscalDateEnding", "N/A")
            operating_cf = safe_float(report.get("operatingCashflow"))
            capex = safe_float(report.get("capitalExpenditures"))
            net_income = safe_float(report.get("netIncome"))
            free_cf = operating_cf - abs(capex) if operating_cf and capex else None

            fcf_values.append(free_cf)

            output.append(
                f"| {date_ending} | {format_large_number(operating_cf)} | "
                f"{format_large_number(abs(capex))} | "
                f"{format_large_number(free_cf)} | "
                f"{format_large_number(net_income)} |"
            )

        # Trend analysis for multi-period
        if (
            len(fcf_values) >= 2
            and fcf_values[0] is not None
            and fcf_values[1] is not None
        ):
            latest_fcf = fcf_values[0]
            prev_fcf = fcf_values[1]
            growth = calculate_qoq_growth(latest_fcf, prev_fcf)
            trend_label = "QoQ" if period == "quarter" else "YoY"

            output.extend(
                [
                    "",
                    "### Trend Analysis",
                    f"* Free Cash Flow {trend_label} change: {growth}",
                ]
            )

            # Calculate average FCF
            valid_fcf = [f for f in fcf_values if f is not None]
            if valid_fcf:
                avg_fcf = sum(valid_fcf) / len(valid_fcf)
                output.append(
                    f"* Average Free Cash Flow: {format_large_number(avg_fcf)}"
                )

        return "\n".join(output)

    @staticmethod
    def format_balance_sheet(
        raw_data: dict[str, Any],
        symbol: str,
        invoked_at: str,
        count: int = 3,
        period: str = "quarter",
    ) -> str:
        """
        Format balance sheet with configurable period selection.

        Args:
            raw_data: Raw Alpha Vantage BALANCE_SHEET response
            symbol: Stock symbol
            invoked_at: ISO timestamp
            count: Number of periods to return (default: 3)
            period: "quarter" for quarterly, "year" for annual (default: "quarter")

        Returns:
            Rich markdown with balance sheet data for specified periods
        """
        header = generate_metadata_header(
            tool_name="Balance Sheet Analysis",
            symbol=symbol,
            invoked_at=invoked_at,
            data_source="BALANCE_SHEET",
        )

        annual_reports = raw_data.get("annualReports", [])
        quarterly_reports = raw_data.get("quarterlyReports", [])

        # Select data based on period type
        if period == "year":
            reports = annual_reports[:count]
            period_label = f"Latest {count} Annual" if count > 1 else "Latest Annual"
        else:
            reports = quarterly_reports[:count]
            period_label = f"Latest {count} Quarters" if count > 1 else "Latest Quarter"

        if not reports:
            return (
                f"{header}\n## Balance Sheet - {symbol}\n\n"
                f"No balance sheet data available for {symbol}"
            )

        output = [
            header,
            f"## Balance Sheet - {symbol}",
            "",
            f"### {period_label}",
            "",
        ]

        # Multi-period table format
        if period == "quarter":
            output.extend(
                [
                    "| Quarter End | Total Assets | Total Liabilities | Equity | Current Ratio |",
                    "|-------------|--------------|-------------------|--------|---------------|",
                ]
            )
        else:
            output.extend(
                [
                    "| Fiscal Year | Total Assets | Total Liabilities | Equity | Current Ratio |",
                    "|-------------|--------------|-------------------|--------|---------------|",
                ]
            )

        for report in reports:
            date_ending = report.get("fiscalDateEnding", "N/A")
            total_assets = safe_float(report.get("totalAssets"))
            total_liabilities = safe_float(report.get("totalLiabilities"))
            equity = safe_float(report.get("totalShareholderEquity"))
            current_assets = safe_float(report.get("currentAssets"))
            current_liabilities = safe_float(report.get("currentLiabilities"))

            current_ratio = (
                current_assets / current_liabilities if current_liabilities > 0 else 0
            )

            output.append(
                f"| {date_ending} | {format_large_number(total_assets)} | "
                f"{format_large_number(total_liabilities)} | "
                f"{format_large_number(equity)} | "
                f"{current_ratio:.2f} |"
            )

        # Add key ratios from latest report
        if reports:
            latest = reports[0]
            total_assets = safe_float(latest.get("totalAssets"))
            total_liabilities = safe_float(latest.get("totalLiabilities"))

            if total_assets > 0 and total_liabilities > 0:
                debt_to_assets = (total_liabilities / total_assets) * 100
                output.extend(
                    [
                        "",
                        "### Key Ratios (Latest)",
                        f"* **Debt-to-Assets:** {debt_to_assets:.1f}% (leverage measure)",
                    ]
                )

        return "\n".join(output)
