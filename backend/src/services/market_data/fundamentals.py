"""
Company fundamentals and financial statements.

yfinance is the primary source (free, no quota). Alpha Vantage's free tier is
both rate-limited (25 req/day) and most fundamentals endpoints have been moved
behind the premium paywall — they return a single-key payload of the form
`{"Information": "premium endpoint..."}` for free keys, which fails the same
"Symbol not in data" check as a real 404. So yfinance must run first; AV is
attempted only as a fallback when a key is configured.

The Alpha Vantage fallback bodies live in `fundamentals_av.py` to keep this
file under the 500-line cap; this module owns the dispatch + logging.
"""

import json
from io import StringIO
from typing import Any

import pandas as pd
import structlog

from . import fundamentals_av, yfinance_fundamentals, yfinance_movers
from .base import AlphaVantageBase

logger = structlog.get_logger()


class FundamentalsMixin(AlphaVantageBase):
    """Methods for company fundamentals, financial statements, and earnings data."""

    async def get_company_overview(self, symbol: str) -> dict[str, Any]:
        """Company overview. yfinance primary, AV fallback."""
        try:
            data = await yfinance_fundamentals.get_company_overview(symbol)
            logger.info(
                "Company overview via yfinance",
                symbol=symbol,
                company_name=data.get("Name", "N/A"),
            )
            return data
        except Exception as yf_err:
            if not self.api_key:
                logger.error("yfinance overview failed (no AV fallback)", symbol=symbol, error=str(yf_err))
                raise
            logger.warning("yfinance overview failed, trying Alpha Vantage", symbol=symbol, error=str(yf_err))
        try:
            return await fundamentals_av.fetch_company_overview(self, symbol)
        except Exception as e:
            logger.error("Company overview fetch failed", symbol=symbol, error=str(e))
            raise

    async def get_cash_flow(self, symbol: str) -> dict[str, Any]:
        """Cash flow. yfinance primary, AV fallback."""
        try:
            data = await yfinance_fundamentals.get_cash_flow(symbol)
            logger.info(
                "Cash flow via yfinance",
                symbol=symbol,
                annual_reports=len(data.get("annualReports", [])),
                quarterly_reports=len(data.get("quarterlyReports", [])),
            )
            return data
        except Exception as yf_err:
            if not self.api_key:
                logger.error("yfinance cash flow failed (no AV fallback)", symbol=symbol, error=str(yf_err))
                raise
            logger.warning("yfinance cash flow failed, trying Alpha Vantage", symbol=symbol, error=str(yf_err))
        try:
            return await fundamentals_av.fetch_cash_flow(self, symbol)
        except Exception as e:
            logger.error("Cash flow fetch failed", symbol=symbol, error=str(e))
            raise

    async def get_balance_sheet(self, symbol: str) -> dict[str, Any]:
        """Balance sheet. yfinance primary, AV fallback."""
        try:
            data = await yfinance_fundamentals.get_balance_sheet(symbol)
            logger.info(
                "Balance sheet via yfinance",
                symbol=symbol,
                annual_reports=len(data.get("annualReports", [])),
                quarterly_reports=len(data.get("quarterlyReports", [])),
            )
            return data
        except Exception as yf_err:
            if not self.api_key:
                logger.error("yfinance balance sheet failed (no AV fallback)", symbol=symbol, error=str(yf_err))
                raise
            logger.warning("yfinance balance sheet failed, trying Alpha Vantage", symbol=symbol, error=str(yf_err))
        try:
            return await fundamentals_av.fetch_balance_sheet(self, symbol)
        except Exception as e:
            logger.error("Balance sheet fetch failed", symbol=symbol, error=str(e))
            raise

    async def get_news_sentiment(
        self,
        tickers: str | None = None,
        topics: str | None = None,
        limit: int = 50,
        sort: str = "LATEST",
    ) -> dict[str, Any]:
        """News + sentiment. yfinance primary (uses local VADER for sentiment),
        AV fallback when a single ticker is requested. Topic-based queries
        require AV — no equivalent in yfinance."""
        if tickers and not topics:
            try:
                data = await yfinance_fundamentals.get_news_sentiment(tickers, limit=limit)
                logger.info("News sentiment via yfinance", tickers=tickers, news_count=len(data.get("feed", [])))
                return data
            except Exception as yf_err:
                if not self.api_key:
                    logger.error("yfinance news failed (no AV fallback)", tickers=tickers, error=str(yf_err))
                    raise
                logger.warning("yfinance news failed, trying Alpha Vantage", tickers=tickers, error=str(yf_err))
        try:
            return await fundamentals_av.fetch_news_sentiment(self, tickers, topics, limit, sort)
        except Exception as e:
            logger.error("News sentiment fetch failed", tickers=tickers, topics=topics, error=str(e))
            raise

    async def get_top_gainers_losers(self) -> dict[str, Any]:
        """Top gainers/losers/most active. yfinance primary, AV fallback."""
        try:
            data = await yfinance_movers.get_market_movers(count=20)
            logger.info(
                "Market movers via yfinance",
                gainers_count=len(data.get("top_gainers", [])),
                losers_count=len(data.get("top_losers", [])),
                active_count=len(data.get("most_actively_traded", [])),
            )
            return data
        except Exception as yf_err:
            if not self.api_key:
                logger.error("yfinance movers failed (no AV fallback)", error=str(yf_err))
                raise
            logger.warning("yfinance movers failed, trying Alpha Vantage", error=str(yf_err))
        try:
            return await fundamentals_av.fetch_top_gainers_losers(self)
        except Exception as e:
            logger.error("Market movers fetch failed", error=str(e))
            raise

    async def get_earnings(self, symbol: str) -> dict[str, Any]:
        """
        Get company earnings data using EARNINGS endpoint.

        Returns annual and quarterly earnings (EPS) history including:
        - reportedEPS, estimatedEPS, surprise, surprisePercentage
        - fiscalDateEnding, reportedDate

        Args:
            symbol: Stock symbol

        Returns:
            Dict with annualEarnings and quarterlyEarnings lists
        """
        try:
            response = await self.client.get(
                self.base_url,
                params={
                    "function": "EARNINGS",
                    "symbol": symbol,
                    "apikey": self.api_key,
                },
            )

            if response.status_code != 200:
                sanitized_text = self._sanitize_text(response.text)
                raise ValueError(
                    f"Alpha Vantage API error: {response.status_code} - {sanitized_text}"
                )

            data = response.json()

            if "annualEarnings" not in data and "quarterlyEarnings" not in data:
                raise ValueError(f"No earnings data for symbol: {symbol}")

            logger.info(
                "Earnings data fetched",
                symbol=symbol,
                annual_count=len(data.get("annualEarnings", [])),
                quarterly_count=len(data.get("quarterlyEarnings", [])),
            )

            return data  # type: ignore[no-any-return]

        except Exception as e:
            logger.error("Earnings fetch failed", symbol=symbol, error=str(e))
            raise

    async def get_insider_transactions(
        self, symbol: str, limit: int = 50
    ) -> dict[str, Any]:
        """
        Get insider transactions (executive buy/sell activity).

        Returns CSV data from INSIDER_TRANSACTIONS endpoint.
        Filters to most recent transactions for context efficiency.

        Args:
            symbol: Stock ticker symbol
            limit: Maximum number of transactions to return (default: 50)

        Returns:
            Dict with 'symbol' and 'data' list containing transaction records
        """
        try:
            response = await self.client.get(
                self.base_url,
                params={
                    "function": "INSIDER_TRANSACTIONS",
                    "symbol": symbol,
                    "apikey": self.api_key,
                },
            )

            if response.status_code != 200:
                sanitized_text = self._sanitize_text(response.text)
                raise ValueError(
                    f"Alpha Vantage API error: {response.status_code} - {sanitized_text}"
                )

            # Parse CSV response
            csv_text = response.text.strip()

            if not csv_text or "Error" in csv_text[:100]:
                sanitized = self._sanitize_text(csv_text[:200])
                raise ValueError(
                    f"No insider transaction data for symbol: {symbol}. Response: {sanitized}"
                )

            # Parse CSV using pandas
            df = pd.read_csv(
                StringIO(csv_text),
                on_bad_lines="skip",
            )

            if df.empty:
                logger.warning("No insider transactions found", symbol=symbol)
                return {"symbol": symbol, "data": []}

            # Convert to list of dicts and limit to recent transactions
            transactions = df.head(limit).to_dict("records")

            logger.info(
                "Insider transactions fetched",
                symbol=symbol,
                total_count=len(df),
                returned_count=len(transactions),
            )

            return {"symbol": symbol, "data": transactions}

        except Exception as e:
            logger.error(
                "Insider transactions fetch failed", symbol=symbol, error=str(e)
            )
            raise

    async def get_etf_profile(self, symbol: str) -> dict[str, Any]:
        """
        Get ETF profile with holdings and sector allocation.

        Uses ETF_PROFILE endpoint to return holdings (top constituents)
        and sector breakdown for exchange-traded funds.

        **Caching**: ETF profiles change infrequently, cached for 24 hours.

        Args:
            symbol: ETF ticker symbol (e.g., "QQQ", "SOXS", "SPY")

        Returns:
            Dict with net_assets, holdings, sectors, leveraged flag, etc.
        """
        # Check cache first (24h TTL - ETF profiles rarely change)
        cache_key = f"etf_profile:{symbol}"
        if self.redis_cache:
            cached_data = await self.redis_cache.get(cache_key)
            if cached_data:
                logger.info("ETF profile cache hit", symbol=symbol)
                return json.loads(cached_data)  # type: ignore[no-any-return]

        try:
            response = await self.client.get(
                self.base_url,
                params={
                    "function": "ETF_PROFILE",
                    "symbol": symbol,
                    "apikey": self.api_key,
                },
            )

            if response.status_code != 200:
                sanitized_text = self._sanitize_text(response.text)
                raise ValueError(
                    f"Alpha Vantage API error: {response.status_code} - {sanitized_text}"
                )

            data = response.json()

            if not data or "Error Message" in data:
                sanitized = self._sanitize_response(data)
                raise ValueError(
                    f"No ETF profile data for symbol: {symbol}. Response: {sanitized}"
                )

            result = {"symbol": symbol, **data}

            # Cache for 24 hours (ETF profiles change infrequently)
            if self.redis_cache:
                await self.redis_cache.set(
                    cache_key,
                    json.dumps(result),
                    ttl=86400,  # 24 hours
                )

            logger.info(
                "ETF profile fetched and cached",
                symbol=symbol,
                holdings_count=len(data.get("holdings", [])),
                sectors_count=len(data.get("sectors", [])),
            )

            return result

        except Exception as e:
            logger.error("ETF profile fetch failed", symbol=symbol, error=str(e))
            raise

    async def get_ipo_calendar(self) -> list[dict[str, Any]]:
        """
        Get upcoming IPOs using IPO_CALENDAR endpoint.

        Returns CSV data with scheduled IPOs including:
        - symbol, name, ipoDate, priceRangeLow, priceRangeHigh
        - currency, exchange

        Returns:
            List of dicts with IPO details
        """
        try:
            response = await self.client.get(
                self.base_url,
                params={
                    "function": "IPO_CALENDAR",
                    "apikey": self.api_key,
                },
            )

            if response.status_code != 200:
                sanitized_text = self._sanitize_text(response.text)
                raise ValueError(
                    f"Alpha Vantage API error: {response.status_code} - {sanitized_text}"
                )

            csv_text = response.text

            # Check for error messages in response
            if csv_text.startswith("{"):
                data = json.loads(csv_text)
                sanitized = self._sanitize_response(data)
                raise ValueError(f"IPO Calendar API error: {sanitized}")

            # Parse CSV using pandas
            if (
                not csv_text.strip()
                or csv_text.strip()
                == "symbol,name,ipoDate,priceRangeLow,priceRangeHigh,currency,exchange"
            ):
                logger.warning("No upcoming IPOs found in calendar")
                return []

            df = pd.read_csv(
                StringIO(csv_text),
                on_bad_lines="skip",
            )

            if df.empty:
                logger.warning("No IPOs in calendar")
                return []

            # Convert to list of dicts
            ipos = df.to_dict("records")

            logger.info(
                "IPO calendar fetched",
                ipo_count=len(ipos),
            )

            return ipos

        except Exception as e:
            logger.error("IPO calendar fetch failed", error=str(e))
            raise
