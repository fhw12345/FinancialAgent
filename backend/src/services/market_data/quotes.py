"""
Stock quotes and symbol search methods for Alpha Vantage service.

W7: When no Alpha Vantage API key is configured, falls back to yfinance
(free, unlimited) so the app works out-of-the-box without paid keys.
"""

import asyncio
from typing import Any

import pandas as pd
import structlog
import yfinance as yf

from .base import AlphaVantageBase

logger = structlog.get_logger()


def _yf_quote_sync(symbol: str) -> dict[str, Any]:
    """Synchronous yfinance quote fetch — runs in thread pool.

    Uses prepost=True so the latest bar reflects extended-hours trading when
    the regular session is closed. Derives session from the last bar's
    timestamp via get_market_session(). In pre/post session, ``price`` is the
    latest non-zero-volume bar close (regularMarketPrice / currentPrice lag
    extended hours).
    """
    # Function-local import to avoid circular import (this module is imported
    # by services.market_data.__init__ which defines get_market_session).
    from src.services.data_manager.manager import _extended_hours_price

    from . import get_market_session

    ticker = yf.Ticker(symbol)
    info = ticker.info or {}
    # Fall back to recent history if .info is sparse. prepost=True so the
    # last bar can be a pre/post extended-hours bar when RTH is closed.
    hist = ticker.history(period="2d", prepost=True)
    last_close = float(hist["Close"].iloc[-1]) if len(hist) else 0.0
    # Anchor previous_close to the prior RTH close, not the second-to-last
    # bar of the prepost-inclusive history (which can itself be an extended-
    # hours bar with a price far from yesterday's settlement). yfinance .info
    # exposes both keys; fall back to hist[-2] only when neither is present.
    info_prev = info.get("regularMarketPreviousClose") or info.get("previousClose")
    if info_prev:
        prev_close = float(info_prev)
    elif len(hist) >= 2:
        prev_close = float(hist["Close"].iloc[-2])
    else:
        prev_close = last_close
    open_p = float(hist["Open"].iloc[-1]) if len(hist) else 0.0
    high_p = float(hist["High"].iloc[-1]) if len(hist) else 0.0
    low_p = float(hist["Low"].iloc[-1]) if len(hist) else 0.0
    vol = int(hist["Volume"].iloc[-1]) if len(hist) else int(info.get("volume", 0) or 0)
    last_day = hist.index[-1].strftime("%Y-%m-%d") if len(hist) else ""
    # Derive session from last bar's timestamp. yfinance index entries can
    # be tz-naive; force UTC before handing to get_market_session().
    if len(hist):
        last_ts = hist.index[-1]
        if last_ts.tz is None:
            last_ts = last_ts.tz_localize("UTC")
        session = get_market_session(last_ts)
    else:
        session = "regular"
    fallback_price = float(
        info.get("currentPrice") or info.get("regularMarketPrice") or last_close
    )
    price = _extended_hours_price(hist if len(hist) else None, session, fallback_price)
    change = price - prev_close
    change_pct = (change / prev_close * 100.0) if prev_close else 0.0
    return {
        "symbol": symbol,
        "price": price,
        "volume": vol,
        "latest_trading_day": last_day,
        "previous_close": prev_close,
        "change": change,
        "change_percent": f"{change_pct:.4f}",
        "open": open_p,
        "high": high_p,
        "low": low_p,
        "session": session,
    }


def _yf_search_sync(query: str, limit: int) -> list[dict[str, Any]]:
    """Synchronous yfinance ticker search via Yahoo's search endpoint."""
    try:
        # yfinance doesn't expose search directly; use the lookup endpoint
        from yfinance import Search

        results = Search(query, max_results=limit).quotes or []
    except Exception:
        results = []
    out: list[dict[str, Any]] = []
    for r in results[:limit]:
        sym = r.get("symbol") or ""
        out.append(
            {
                "symbol": sym,
                "name": r.get("shortname") or r.get("longname") or "",
                "type": r.get("quoteType", ""),
                "exchange": r.get("exchange", ""),
                "match_type": (
                    "exact_symbol" if sym.upper() == query.upper() else "fuzzy"
                ),
                "confidence": 1.0 if sym.upper() == query.upper() else 0.5,
            }
        )
    return out


class QuotesMixin(AlphaVantageBase):
    """Methods for stock quotes, symbol search, and market status."""

    async def search_symbols(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        Search for stock symbols using Alpha Vantage SYMBOL_SEARCH.

        Args:
            query: Search query (symbol or company name)
            limit: Maximum number of results

        Returns:
            List of search results with symbol, name, type, region, currency
        """
        # W7: yfinance fallback when no AV key configured
        if not self.api_key:
            results = await asyncio.to_thread(_yf_search_sync, query, limit)
            logger.info(
                "Symbol search via yfinance",
                query=query,
                results_count=len(results),
            )
            return results
        try:
            response = await self.client.get(
                self.base_url,
                params={
                    "function": "SYMBOL_SEARCH",
                    "keywords": query,
                    "apikey": self.api_key,
                },
            )

            if response.status_code != 200:
                sanitized_text = self._sanitize_text(response.text)
                raise ValueError(
                    f"Alpha Vantage API error: {response.status_code} - {sanitized_text}"
                )

            data = response.json()

            if "bestMatches" not in data:
                # Sanitize response to avoid logging API keys
                sanitized = self._sanitize_response(data)
                logger.warning("No matches found", query=query, response=sanitized)
                return []

            matches = data["bestMatches"][:limit]

            # Format results to match API contract
            results = []
            for match in matches:
                match_score = float(match.get("9. matchScore", "0.0"))
                results.append(
                    {
                        "symbol": match.get("1. symbol", ""),
                        "name": match.get("2. name", ""),
                        "type": match.get("3. type", ""),
                        "exchange": match.get(
                            "4. region", ""
                        ),  # Use region as exchange
                        "match_type": "exact_symbol" if match_score >= 0.9 else "fuzzy",
                        "confidence": match_score,
                    }
                )

            logger.info(
                "Symbol search completed",
                query=query,
                results_count=len(results),
            )

            return results

        except Exception as e:
            logger.error("Symbol search failed", query=query, error=str(e))
            raise

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        """
        Get real-time quote. yfinance is the primary source (free, unlimited);
        Alpha Vantage is used only as a fallback when yfinance fails AND a key
        is configured. This ordering is important because AV's free tier no
        longer returns useful data for many endpoints (responses contain only
        an "Information" key advertising premium).
        """
        try:
            result = await asyncio.to_thread(_yf_quote_sync, symbol)
            logger.info("Quote via yfinance", symbol=symbol, price=result["price"])
            return result
        except Exception as yf_err:
            if not self.api_key:
                logger.error("yfinance quote failed (no AV fallback)", symbol=symbol, error=str(yf_err))
                raise
            logger.warning(
                "yfinance quote failed, trying Alpha Vantage",
                symbol=symbol,
                error=str(yf_err),
            )
        try:
            # GLOBAL_QUOTE with entitlement=delayed returns previous day's close during market hours
            # It will show today's close only after market closes
            response = await self.client.get(
                self.base_url,
                params={
                    "function": "GLOBAL_QUOTE",
                    "symbol": symbol,
                    "entitlement": "delayed",
                    "apikey": self.api_key,
                },
            )

            if response.status_code != 200:
                sanitized_text = self._sanitize_text(response.text)
                raise ValueError(
                    f"Alpha Vantage API error: {response.status_code} - {sanitized_text}"
                )

            data = response.json()

            # Handle both standard and delayed response formats
            # Standard: "Global Quote"
            # Delayed: "Global Quote - DATA DELAYED BY 15 MINUTES"
            quote_key = None
            for key in data.keys():
                if key.startswith("Global Quote"):
                    quote_key = key
                    break

            if not quote_key or not data[quote_key]:
                raise ValueError(f"No quote data for symbol: {symbol}")

            quote = data[quote_key]

            logger.info(
                "Quote API response parsed",
                symbol=symbol,
                quote_key=quote_key,
            )

            result = {
                "symbol": quote.get("01. symbol", symbol),
                "price": float(quote.get("05. price", 0)),
                "volume": int(quote.get("06. volume", 0)),
                "latest_trading_day": quote.get("07. latest trading day", ""),
                "previous_close": float(quote.get("08. previous close", 0)),
                "change": float(quote.get("09. change", 0)),
                "change_percent": quote.get("10. change percent", "0%").rstrip("%"),
                "open": float(quote.get("02. open", 0)),
                "high": float(quote.get("03. high", 0)),
                "low": float(quote.get("04. low", 0)),
                # AV GLOBAL_QUOTE returns RTH-only data; stamp session=regular.
                "session": "regular",
            }

            logger.info(
                "Quote fetched",
                symbol=symbol,
                price=result["price"],
            )

            return result

        except Exception as e:
            logger.error("Quote fetch failed", symbol=symbol, error=str(e))
            raise

    async def get_market_status(self, region: str = "United States") -> dict[str, Any]:
        """
        Get global market open/close status from Alpha Vantage MARKET_STATUS API.

        Supports multiple regions for extensibility (US, Hong Kong, China, etc.).

        Args:
            region: Market region to query. Supported values:
                - "United States" (default)
                - "Hong Kong"
                - "Mainland China"
                - "Japan"
                - "United Kingdom"
                - "Germany"
                - And more...

        Returns:
            Dict with market status info:
                - region: Market region name
                - current_status: "open" or "closed"
                - local_open: Local market open time (HH:MM)
                - local_close: Local market close time (HH:MM)
                - primary_exchanges: Exchange names
                - notes: Additional notes (e.g., lunch breaks)
                - local_time: Current local time for that market
                - utc_time: Current UTC time
        """
        # Region to timezone mapping for computing local time
        region_timezones = {
            "United States": "America/New_York",
            "Hong Kong": "Asia/Hong_Kong",
            "Mainland China": "Asia/Shanghai",
            "Japan": "Asia/Tokyo",
            "United Kingdom": "Europe/London",
            "Germany": "Europe/Berlin",
            "France": "Europe/Paris",
            "Canada": "America/Toronto",
            "India": "Asia/Kolkata",
            "Brazil": "America/Sao_Paulo",
            "Mexico": "America/Mexico_City",
            "South Africa": "Africa/Johannesburg",
            "Spain": "Europe/Madrid",
            "Portugal": "Europe/Lisbon",
        }

        try:
            # W7: yfinance fallback — compute status from local time vs market hours
            if not self.api_key:
                tz = region_timezones.get(region, "UTC")
                utc_now = pd.Timestamp.now(tz="UTC")
                local_now = utc_now.tz_convert(tz)
                # Simple heuristic: equity markets open 09:30-16:00 local, Mon-Fri
                is_weekday = local_now.weekday() < 5
                in_hours = (local_now.hour, local_now.minute) >= (9, 30) and (
                    local_now.hour < 16
                )
                status = "open" if (is_weekday and in_hours) else "closed"
                return {
                    "region": region,
                    "current_status": status,
                    "local_open": "09:30",
                    "local_close": "16:00",
                    "primary_exchanges": "NYSE, NASDAQ"
                    if region == "United States"
                    else "",
                    "notes": "yfinance fallback — heuristic schedule",
                    "local_time": local_now.strftime("%Y-%m-%d %H:%M %Z"),
                    "utc_time": utc_now.strftime("%Y-%m-%d %H:%M UTC"),
                }
            response = await self.client.get(
                self.base_url,
                params={
                    "function": "MARKET_STATUS",
                    "apikey": self.api_key,
                },
            )

            if response.status_code != 200:
                sanitized_text = self._sanitize_text(response.text)
                raise ValueError(
                    f"Alpha Vantage API error: {response.status_code} - {sanitized_text}"
                )

            data = response.json()
            markets = data.get("markets", [])

            # Find the requested region
            market_info = None
            for market in markets:
                if (
                    market.get("region") == region
                    and market.get("market_type") == "Equity"
                ):
                    market_info = market
                    break

            if not market_info:
                raise ValueError(f"Market region not found: {region}")

            # Get current times
            utc_now = pd.Timestamp.now(tz="UTC")
            timezone = region_timezones.get(region, "UTC")
            local_now = utc_now.tz_convert(timezone)

            result = {
                "region": region,
                "current_status": market_info.get("current_status", "unknown"),
                "local_open": market_info.get("local_open", ""),
                "local_close": market_info.get("local_close", ""),
                "primary_exchanges": market_info.get("primary_exchanges", ""),
                "notes": market_info.get("notes", ""),
                "local_time": local_now.strftime("%Y-%m-%d %H:%M %Z"),
                "utc_time": utc_now.strftime("%Y-%m-%d %H:%M UTC"),
            }

            logger.info(
                "Market status fetched",
                region=region,
                status=result["current_status"],
            )

            return result

        except Exception as e:
            logger.error("Market status fetch failed", region=region, error=str(e))
            raise
